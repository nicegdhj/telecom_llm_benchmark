import os
from unittest.mock import patch

import pytest

from backend.app.db import get_session
from backend.app.models import Job, Model, Task
from backend.app.services.seed import seed_generic_tasks


def _seed(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    mid = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()["id"]
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    r = client.post("/api/v1/batches", json={
        "name": "b1", "mode": "infer",
        "model_ids": [mid], "task_ids": [tid],
    })
    return r.json()["id"], mid, tid


def test_list_and_get_job(client):
    bid, mid, tid = _seed(client)

    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) >= 1
    jid = jobs[0]["id"]
    r2 = client.get(f"/api/v1/jobs/{jid}")
    assert r2.status_code == 200
    assert r2.json()["type"] == "infer"


def test_get_job_not_found(client):
    r = client.get("/api/v1/jobs/99999")
    assert r.status_code == 404


def test_list_jobs_filter_by_batch_id(client):
    bid, mid, tid = _seed(client)

    r = client.get(f"/api/v1/jobs?batch_id={bid}")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) == 1
    assert jobs[0]["batch_id"] == bid


def test_get_job_log_not_found(client):
    r = client.get("/api/v1/jobs/99999/log")
    assert r.status_code == 404


def test_get_job_log_no_log_path(client):
    bid, mid, tid = _seed(client)
    with get_session() as s:
        job = s.query(Job).filter_by(batch_id=bid).first()
        jid = job.id
        job.log_path = None
    r = client.get(f"/api/v1/jobs/{jid}/log")
    assert r.status_code == 404


def test_get_job_log_file_not_found(client, tmp_path):
    bid, mid, tid = _seed(client)
    with get_session() as s:
        job = s.query(Job).filter_by(batch_id=bid).first()
        jid = job.id
        job.log_path = str(tmp_path / "nonexistent.log")
    r = client.get(f"/api/v1/jobs/{jid}/log")
    assert r.status_code == 404


def test_get_job_log_ok(client, tmp_path):
    bid, mid, tid = _seed(client)
    log_file = tmp_path / "job_test.log"
    log_file.write_text("docker log output here")
    with get_session() as s:
        job = s.query(Job).filter_by(batch_id=bid).first()
        job.log_path = str(log_file)
        s.commit()
        jid = job.id
    r = client.get(f"/api/v1/jobs/{jid}/log")
    assert r.status_code == 200
    assert r.json()["log"] == "docker log output here"


def test_cancel_job_not_found(client):
    r = client.post("/api/v1/jobs/99999/cancel")
    assert r.status_code == 404


def test_cancel_pending_job(client):
    bid, mid, tid = _seed(client)
    with get_session() as s:
        job = s.query(Job).filter_by(batch_id=bid).first()
        jid = job.id
    r = client.post(f"/api/v1/jobs/{jid}/cancel")
    assert r.status_code == 200
    assert r.json()["status"] == "cancelled"
    r2 = client.get(f"/api/v1/jobs/{jid}")
    assert r2.json()["status"] == "cancelled"


def test_cancel_already_done_job(client):
    bid, mid, tid = _seed(client)
    with get_session() as s:
        job = s.query(Job).filter_by(batch_id=bid).first()
        job.status = "success"
        s.commit()
        jid = job.id
    r = client.post(f"/api/v1/jobs/{jid}/cancel")
    assert r.status_code == 400


def test_framework_log_collects_ais_bench_out(client):
    """infer job 的框架日志：定位 outputs/<otid>/details/**/logs/infer/**/*.out 并返回内容。"""
    from datetime import datetime
    from backend.app.config import get_settings
    from backend.app.models import Prediction

    bid, mid, tid = _seed(client)
    otid = "batchX_m1_t1_20260101_000000"

    # 造一个 ais_bench .out 框架日志文件
    settings = get_settings()
    log_file = (settings.workspace_dir / "outputs" / otid /
                "details" / "20260101_000000" / "logs" / "infer" / "gw")
    log_file.mkdir(parents=True, exist_ok=True)
    (log_file / "task_1.out").write_text("FRAMEWORK INTERNAL LOG LINE", encoding="utf-8")

    with get_session() as s:
        p = Prediction(model_id=mid, task_id=tid, status="success",
                       output_task_id=otid, job_id=None)
        s.add(p); s.flush()
        job = Job(type="infer", batch_id=bid, model_id=mid, task_id=tid,
                  params_json={}, status="success", produces_prediction_id=p.id)
        s.add(job); s.commit()
        jid = job.id

    r = client.get(f"/api/v1/jobs/{jid}/framework-log")
    assert r.status_code == 200
    body = r.json()
    assert body["available"] is True
    assert "FRAMEWORK INTERNAL LOG LINE" in body["log"]


def test_framework_log_absent_returns_available_false(client):
    """无产物 / 无 .out 时，available=False。"""
    bid, mid, tid = _seed(client)
    with get_session() as s:
        job = s.query(Job).filter_by(batch_id=bid).first()
        jid = job.id
    r = client.get(f"/api/v1/jobs/{jid}/framework-log")
    assert r.status_code == 200
    assert r.json()["available"] is False
