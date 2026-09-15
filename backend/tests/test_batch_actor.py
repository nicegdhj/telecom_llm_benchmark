from fastapi.testclient import TestClient

from backend.app.db import get_session
from backend.app.main import app
from backend.app.services.user_service import create_user


def _seed_user(name="alice", role="operator"):
    with get_session() as s:
        from backend.app.models import User
        if not s.query(User).filter_by(username=name).first():
            create_user(s, name, "pw", role, None)
            s.commit()


def _seed_model_task():
    with get_session() as s:
        from backend.app.models import Model, Task
        m = Model(name="m1", host="h", port=1, model_name="m",
                  concurrency=1, gen_kwargs_json={}, model_config_key="local_qwen")
        t = Task(key="t1", type="custom", suite_name="s")
        s.add_all([m, t]); s.commit()
        return m.id, t.id


def test_create_batch_records_actor():
    _seed_user("alice", "operator")
    mid, tid = _seed_model_task()
    c = TestClient(app)
    token = c.post("/api/v1/auth/login",
                   json={"username": "alice", "password": "pw"}).json()["session_token"]
    r = c.post("/api/v1/batches",
               headers={"Authorization": f"Bearer {token}"},
               json={"name": "b1", "mode": "all",
                     "model_ids": [mid], "task_ids": [tid]})
    assert r.status_code == 201
    body = r.json()
    assert body["created_by"]["username"] == "alice"
    assert body["last_modified_by"]["username"] == "alice"

    # 关联 job 也带 created_by
    r = c.get("/api/v1/jobs",
              headers={"Authorization": f"Bearer {token}"},
              params={"batch_id": body["id"]})
    jobs = r.json()
    assert all(j["created_by"]["username"] == "alice" for j in jobs)
