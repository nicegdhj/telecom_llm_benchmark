"""GET /evaluations/search 测试。"""
from datetime import datetime

from backend.app.db import get_session
from backend.app.models import Evaluation, Job, Prediction
from backend.app.services.seed import seed_generic_tasks


def _seed_batch(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    mid = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()["id"]
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    bid = client.post("/api/v1/batches", json={
        "name": "b1", "mode": "all", "model_ids": [mid], "task_ids": [tid],
    }).json()["id"]
    return bid, mid, tid


def _make_eval(bid, mid, tid, *, accuracy, status="success"):
    with get_session() as s:
        jp = Job(type="infer", batch_id=bid, model_id=mid, task_id=tid,
                 params_json={}, status="success", created_at=datetime.utcnow())
        s.add(jp); s.flush()
        p = Prediction(model_id=mid, task_id=tid, status="success",
                       num_samples=10, duration_sec=1.0, job_id=jp.id,
                       version_label="v1_infer", finished_at=datetime.utcnow())
        s.add(p); s.flush()
        je = Job(type="eval", batch_id=bid, model_id=mid, task_id=tid,
                 params_json={}, status="success", created_at=datetime.utcnow())
        s.add(je); s.flush()
        e = Evaluation(prediction_id=p.id, eval_version="eval_init",
                       status=status, accuracy=accuracy, num_samples=10,
                       duration_sec=0.5, job_id=je.id,
                       version_label="v1_score", finished_at=datetime.utcnow())
        s.add(e); s.flush()
        je.produces_evaluation_id = e.id
        s.commit()
        return e.id


def test_search_basic(client):
    bid, mid, tid = _seed_batch(client)
    _make_eval(bid, mid, tid, accuracy=70.0)
    _make_eval(bid, mid, tid, accuracy=85.0)
    r = client.get("/api/v1/evaluations/search")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 2
    assert {row["model_name"] for row in rows} == {"m1"}
    assert {row["accuracy"] for row in rows} == {70.0, 85.0}
    assert rows[0]["batch_name"] == "b1"
    assert rows[0]["version_label"] == "v1_score"


def test_search_filter_by_status(client):
    bid, mid, tid = _seed_batch(client)
    _make_eval(bid, mid, tid, accuracy=70.0, status="success")
    _make_eval(bid, mid, tid, accuracy=None, status="failed")
    r = client.get("/api/v1/evaluations/search?status=success")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    assert rows[0]["accuracy"] == 70.0


def test_search_filter_by_batch(client):
    bid, mid, tid = _seed_batch(client)
    _make_eval(bid, mid, tid, accuracy=70.0)
    r = client.get(f"/api/v1/evaluations/search?batch_ids={bid}")
    assert r.status_code == 200
    assert len(r.json()) == 1
    r2 = client.get("/api/v1/evaluations/search?batch_ids=99999")
    assert r2.status_code == 200
    assert len(r2.json()) == 0


def test_search_limit(client):
    bid, mid, tid = _seed_batch(client)
    for _ in range(5):
        _make_eval(bid, mid, tid, accuracy=70.0)
    r = client.get("/api/v1/evaluations/search?limit=3")
    assert r.status_code == 200
    assert len(r.json()) == 3


def test_search_filter_by_eval_ids(client):
    """eval_ids 精确查询：只返回指定 id，供测评分析对比视图按选中项精确取数。"""
    bid, mid, tid = _seed_batch(client)
    e1 = _make_eval(bid, mid, tid, accuracy=70.0)
    e2 = _make_eval(bid, mid, tid, accuracy=85.0)
    _make_eval(bid, mid, tid, accuracy=90.0)  # 不选

    r = client.get(f"/api/v1/evaluations/search?eval_ids={e1}&eval_ids={e2}")
    assert r.status_code == 200
    rows = r.json()
    assert {row["id"] for row in rows} == {e1, e2}
