from backend.app.db import get_session
from backend.app.models import BatchCell, BatchRevision, Job
from backend.app.services.seed import seed_generic_tasks


def _seed(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    mid = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()["id"]
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    bid = client.post("/api/v1/batches", json={
        "name": "b", "mode": "infer",
        "model_ids": [mid], "task_ids": [tid]}).json()["id"]
    return bid, mid, tid


def test_rerun_infer_creates_job(client):
    bid, mid, tid = _seed(client)
    r = client.post(f"/api/v1/batches/{bid}/rerun", json={
        "model_ids": [mid], "task_ids": [tid], "what": "infer"})
    assert r.status_code == 201
    body = r.json()
    assert body["batch_id"] == bid
    assert body["jobs_created"] == 1

    with get_session() as s:
        jobs = s.query(Job).filter_by(batch_id=bid, type="infer").all()
        assert len(jobs) == 2  # 原始 1 个 + 新 1 个
        revs = s.query(BatchRevision).filter_by(batch_id=bid).all()
        assert len(revs) == 2  # create + rerun
        assert revs[1].change_type == "rerun"


def test_rerun_eval_creates_job(client):
    bid, mid, tid = _seed(client)
    r = client.post(f"/api/v1/batches/{bid}/rerun", json={
        "model_ids": [mid], "task_ids": [tid], "what": "eval"})
    assert r.status_code == 201
    body = r.json()
    assert body["jobs_created"] == 1

    with get_session() as s:
        jobs = s.query(Job).filter_by(batch_id=bid, type="eval").all()
        assert len(jobs) == 1
        job = jobs[0]
        assert job.dependency_job_id is None  # eval-only 无依赖


def test_rerun_both_creates_two_jobs(client):
    bid, mid, tid = _seed(client)
    r = client.post(f"/api/v1/batches/{bid}/rerun", json={
        "model_ids": [mid], "task_ids": [tid], "what": "both"})
    assert r.status_code == 201
    body = r.json()
    assert body["jobs_created"] == 2

    with get_session() as s:
        jobs = s.query(Job).filter_by(batch_id=bid).all()
        types = sorted(j.type for j in jobs)
        assert types == ["eval", "infer", "infer"]


def test_rerun_with_dataset_version(client):
    bid, mid, tid = _seed(client)
    # 先上传一个数据集版本
    import io
    content = b'{"x": 1}\n'
    r = client.post(
        f"/api/v1/tasks/{tid}/datasets",
        data={"tag": "v1"},
        files={"file": ("data.jsonl", io.BytesIO(content), "application/octet-stream")},
    )
    dvid = r.json()["id"]

    r = client.post(f"/api/v1/batches/{bid}/rerun", json={
        "model_ids": [mid], "task_ids": [tid], "what": "infer",
        "dataset_version_id": dvid})
    assert r.status_code == 201

    with get_session() as s:
        cell = s.get(BatchCell, (bid, mid, tid))
        assert cell.dataset_version_id == dvid


def test_rerun_batch_not_found(client):
    r = client.post("/api/v1/batches/99999/rerun", json={
        "model_ids": [1], "task_ids": [1], "what": "infer"})
    assert r.status_code == 404


def test_rerun_cell_not_found(client):
    bid, mid, tid = _seed(client)
    r = client.post(f"/api/v1/batches/{bid}/rerun", json={
        "model_ids": [mid], "task_ids": [99999], "what": "infer"})
    assert r.status_code == 400
