from backend.app.db import get_session
from backend.app.models import BatchCell, BatchRevision, Job
from backend.app.services.seed import seed_generic_tasks


def _prep(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    m = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()
    t = client.get("/api/v1/tasks").json()[0]
    return m["id"], t["id"]


def test_create_batch_generates_cells_jobs_revision(client):
    mid, tid = _prep(client)
    r = client.post("/api/v1/batches", json={
        "name": "round-1",
        "mode": "all",
        "model_ids": [mid],
        "task_ids": [tid],
    })
    assert r.status_code == 201
    bid = r.json()["id"]

    with get_session() as s:
        cells = s.query(BatchCell).filter_by(batch_id=bid).all()
        assert len(cells) == 1
        revs = s.query(BatchRevision).filter_by(batch_id=bid).all()
        assert len(revs) == 1
        assert revs[0].rev_num == 1
        assert revs[0].change_type == "create"
        jobs = s.query(Job).filter_by(batch_id=bid).all()
        assert len(jobs) == 2
        types = sorted(j.type for j in jobs)
        assert types == ["eval", "infer"]


def test_create_batch_mode_infer_only_creates_infer_jobs(client):
    mid, tid = _prep(client)
    r = client.post("/api/v1/batches", json={
        "name": "infer-only",
        "mode": "infer",
        "model_ids": [mid],
        "task_ids": [tid],
    })
    bid = r.json()["id"]
    with get_session() as s:
        jobs = s.query(Job).filter_by(batch_id=bid).all()
        assert len(jobs) == 1
        assert jobs[0].type == "infer"


def test_create_batch_mode_eval_only_creates_eval_jobs(client):
    mid, tid = _prep(client)
    r = client.post("/api/v1/batches", json={
        "name": "eval-only",
        "mode": "eval",
        "model_ids": [mid],
        "task_ids": [tid],
    })
    bid = r.json()["id"]
    with get_session() as s:
        jobs = s.query(Job).filter_by(batch_id=bid).all()
        assert len(jobs) == 1
        assert jobs[0].type == "eval"
        assert jobs[0].dependency_job_id is None
