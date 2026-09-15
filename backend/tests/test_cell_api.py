"""Cell 级 API 测试：详情 / 切指针 / 单 cell 重跑（含 eval-only 的 source 校验）。"""
from datetime import datetime

from backend.app.db import get_session
from backend.app.models import (
    BatchCell, Evaluation, Job, Prediction,
)
from backend.app.services.seed import seed_generic_tasks


def _seed_batch(client):
    """建一个最小批次：1 model × 1 task；返回 (bid, mid, tid)。"""
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    mid = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()["id"]
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    r = client.post("/api/v1/batches", json={
        "name": "b1", "mode": "all",
        "model_ids": [mid], "task_ids": [tid],
    })
    return r.json()["id"], mid, tid


def _add_pred(bid, mid, tid, *, label, status="success"):
    """在 DB 直接插一条 Prediction + 关联 Job，模拟历史产物。"""
    with get_session() as s:
        j = Job(type="infer", batch_id=bid, model_id=mid, task_id=tid,
                params_json={}, status=status, version_label=label,
                created_at=datetime.utcnow())
        s.add(j)
        s.flush()
        p = Prediction(model_id=mid, task_id=tid, status=status,
                       num_samples=100, duration_sec=10.0,
                       job_id=j.id, version_label=label,
                       output_task_id=f"out_{label}",
                       output_path="/tmp/out", finished_at=datetime.utcnow())
        s.add(p)
        s.flush()
        j.produces_prediction_id = p.id
        s.commit()
        return p.id


def _add_eval(bid, mid, tid, pred_id, *, label, accuracy=80.0):
    with get_session() as s:
        j = Job(type="eval", batch_id=bid, model_id=mid, task_id=tid,
                params_json={}, status="success", version_label=label,
                created_at=datetime.utcnow())
        s.add(j)
        s.flush()
        e = Evaluation(prediction_id=pred_id, eval_version="eval_init",
                       status="success", accuracy=accuracy, num_samples=100,
                       duration_sec=2.0, job_id=j.id, version_label=label,
                       finished_at=datetime.utcnow())
        s.add(e)
        s.flush()
        j.produces_evaluation_id = e.id
        s.commit()
        return e.id


def test_cell_detail_returns_history(client):
    bid, mid, tid = _seed_batch(client)
    p1 = _add_pred(bid, mid, tid, label="v1_infer")
    p2 = _add_pred(bid, mid, tid, label="v2_infer")
    _add_eval(bid, mid, tid, p2, label="v1_score", accuracy=88.0)

    r = client.get(f"/api/v1/batches/{bid}/cells/{mid}/{tid}")
    assert r.status_code == 200
    d = r.json()
    assert d["batch_id"] == bid and d["model_id"] == mid and d["task_id"] == tid
    # history 含 seed 阶段 create_batch 自动建的 2 job(pending) + 我们手工插的 3 job = 5
    labels = [h["version_label"] for h in d["history"] if h["version_label"]]
    assert "v1_infer" in labels and "v2_infer" in labels and "v1_score" in labels
    eval_item = next(h for h in d["history"] if h["kind"] == "eval" and h["evaluation_id"])
    assert eval_item["accuracy"] == 88.0
    assert eval_item["based_on_infer"] == "v2_infer"


def test_cell_detail_404(client):
    r = client.get("/api/v1/batches/9999/cells/1/1")
    assert r.status_code == 404


def test_switch_pointer_ok(client):
    bid, mid, tid = _seed_batch(client)
    p1 = _add_pred(bid, mid, tid, label="v1_infer")
    p2 = _add_pred(bid, mid, tid, label="v2_infer")

    r = client.put(f"/api/v1/batches/{bid}/cells/{mid}/{tid}/pointer",
                   json={"current_prediction_id": p1, "current_evaluation_id": None})
    assert r.status_code == 200
    assert r.json()["current_prediction_id"] == p1
    with get_session() as s:
        cell = s.get(BatchCell, (bid, mid, tid))
        assert cell.current_prediction_id == p1


def test_switch_pointer_rejects_eval_inconsistent(client):
    bid, mid, tid = _seed_batch(client)
    p1 = _add_pred(bid, mid, tid, label="v1_infer")
    p2 = _add_pred(bid, mid, tid, label="v2_infer")
    e1 = _add_eval(bid, mid, tid, p1, label="v1_score")  # 基于 p1

    # 试图把 prediction 切到 p2，但 evaluation 还是 e1（基于 p1）→ 拒绝
    r = client.put(f"/api/v1/batches/{bid}/cells/{mid}/{tid}/pointer",
                   json={"current_prediction_id": p2, "current_evaluation_id": e1})
    assert r.status_code == 400
    assert "not based on the selected prediction" in r.json()["detail"]


def test_switch_pointer_prediction_not_in_cell(client):
    bid, mid, tid = _seed_batch(client)
    # 插一条不属于该 cell 的 prediction (mid=999)
    with get_session() as s:
        j = Job(type="infer", batch_id=bid, model_id=999, task_id=tid,
                params_json={}, status="success", created_at=datetime.utcnow())
        s.add(j)
        s.flush()
        p = Prediction(model_id=999, task_id=tid, status="success", job_id=j.id,
                       finished_at=datetime.utcnow())
        s.add(p)
        s.commit()
        pid = p.id

    r = client.put(f"/api/v1/batches/{bid}/cells/{mid}/{tid}/pointer",
                   json={"current_prediction_id": pid})
    assert r.status_code == 400


def test_rerun_cell_eval_requires_source(client):
    bid, mid, tid = _seed_batch(client)
    r = client.post(f"/api/v1/batches/{bid}/cells/{mid}/{tid}/rerun",
                    json={"what": "eval"})
    assert r.status_code == 400
    assert "source_prediction_id" in r.json()["detail"]


def test_rerun_cell_eval_with_valid_source(client):
    bid, mid, tid = _seed_batch(client)
    p1 = _add_pred(bid, mid, tid, label="v1_infer")
    r = client.post(f"/api/v1/batches/{bid}/cells/{mid}/{tid}/rerun",
                    json={"what": "eval", "source_prediction_id": p1})
    assert r.status_code == 201
    body = r.json()
    assert body["jobs_created"] == 1
    # 新 eval job 应带 source_prediction_id
    with get_session() as s:
        j = s.get(Job, body["job_ids"][0])
        assert j.type == "eval"
        assert j.params_json["source_prediction_id"] == p1


def test_rerun_cell_eval_rejects_wrong_source(client):
    bid, mid, tid = _seed_batch(client)
    # 别的 cell 的 prediction
    with get_session() as s:
        j = Job(type="infer", batch_id=bid, model_id=999, task_id=tid,
                params_json={}, status="success", created_at=datetime.utcnow())
        s.add(j)
        s.flush()
        p = Prediction(model_id=999, task_id=tid, status="success", job_id=j.id,
                       finished_at=datetime.utcnow())
        s.add(p)
        s.commit()
        pid = p.id

    r = client.post(f"/api/v1/batches/{bid}/cells/{mid}/{tid}/rerun",
                    json={"what": "eval", "source_prediction_id": pid})
    assert r.status_code == 400


def test_rerun_cell_both(client):
    bid, mid, tid = _seed_batch(client)
    r = client.post(f"/api/v1/batches/{bid}/cells/{mid}/{tid}/rerun",
                    json={"what": "both"})
    assert r.status_code == 201
    assert r.json()["jobs_created"] == 2  # infer + eval


def test_rerun_cell_infer_rejects_source_arg(client):
    bid, mid, tid = _seed_batch(client)
    p1 = _add_pred(bid, mid, tid, label="v1_infer")
    r = client.post(f"/api/v1/batches/{bid}/cells/{mid}/{tid}/rerun",
                    json={"what": "infer", "source_prediction_id": p1})
    assert r.status_code == 400
