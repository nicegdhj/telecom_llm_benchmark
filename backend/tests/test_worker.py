import asyncio
from unittest.mock import patch, MagicMock

import pytest

from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.models import Job, Model, Task
from backend.app.services import worker
from backend.app.services.worker import run_pending_jobs_once, wait_inflight
from backend.app.services.seed import seed_generic_tasks


async def _seed(client, n_models=1):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    mids = [
        client.post("/api/v1/models", json={
            "name": f"m{i}", "host": "h", "port": 1, "model_name": "x"}).json()["id"]
        for i in range(n_models)
    ]
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    r = client.post("/api/v1/batches", json={
        "name": "b1", "mode": "infer",
        "model_ids": mids, "task_ids": [tid],
    })
    return r.json()["id"], mids, tid


async def test_worker_picks_and_runs_pending_job(client):
    bid, mids, tid = await _seed(client)

    fake_proc = MagicMock()
    fake_proc.pid = 12345
    fake_proc.returncode = 0
    fake_proc.wait.return_value = 0

    with patch(
        "backend.app.services.worker.subprocess.Popen",
        return_value=fake_proc,
    ) as popen, patch(
        "backend.app.services.worker.scan_infer_output",
        return_value={"output_path": "/tmp", "num_samples": 100},
    ):
        await run_pending_jobs_once()
        await wait_inflight()   # 派发已改为后台并行，需等在途 job 跑完再断言

    with get_session() as s:
        job = s.query(Job).filter_by(batch_id=bid).first()
        assert job.status == "success"
        assert job.returncode == 0
        popen.assert_called_once()


async def test_respects_global_concurrency_limit(client, monkeypatch):
    """全局上限=2 时，3 个 pending job 一轮只并行启动 2 个，第 3 个仍 pending。"""
    bid, mids, tid = await _seed(client, n_models=3)
    monkeypatch.setattr(get_settings(), "default_job_concurrency", 2)

    gate = asyncio.Event()
    started: list[int] = []

    async def fake_run_infer(db, job, settings):
        started.append(job.id)
        await gate.wait()       # 挂住，模拟长任务，占住并发槽

    monkeypatch.setattr(worker, "_run_infer", fake_run_infer)

    try:
        await run_pending_jobs_once()
        await asyncio.sleep(0)  # 让已派发的后台 task 运行到 gate.wait()

        with get_session() as s:
            jobs = s.query(Job).filter_by(batch_id=bid).all()
            running = [j for j in jobs if j.status == "running"]
            pending = [j for j in jobs if j.status == "pending"]
        assert len(jobs) == 3
        assert len(running) == 2          # 恰好领取/启动 2 个（上限）
        assert len(pending) == 1          # 第 3 个被上限挡住
        assert len(started) == 2
        assert len(set(started)) == 2     # 无重复领取
    finally:
        gate.set()
        await wait_inflight()


async def test_fills_remaining_slot_after_one_finishes(client, monkeypatch):
    """上限=2、已有 2 个 running 占满时，新一轮不再领取；释放后才补位。"""
    bid, mids, tid = await _seed(client, n_models=3)
    monkeypatch.setattr(get_settings(), "default_job_concurrency", 2)

    gate = asyncio.Event()
    started: list[int] = []

    async def fake_run_infer(db, job, settings):
        started.append(job.id)
        await gate.wait()

    monkeypatch.setattr(worker, "_run_infer", fake_run_infer)

    try:
        await run_pending_jobs_once()     # 启动 2 个
        await asyncio.sleep(0)
        await run_pending_jobs_once()     # 已满，不应再启动
        await asyncio.sleep(0)
        assert len(started) == 2          # 仍是 2，上限生效
    finally:
        gate.set()
        await wait_inflight()
