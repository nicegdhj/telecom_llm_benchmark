from fastapi.testclient import TestClient

from backend.app.db import get_session
from backend.app.main import app
from backend.app.services.user_service import create_user


def _seed_users():
    with get_session() as s:
        from backend.app.models import User
        if not s.query(User).filter_by(username="alice_op").first():
            create_user(s, "alice_op", "pw", "operator", None)
        if not s.query(User).filter_by(username="bob_viewer").first():
            create_user(s, "bob_viewer", "pw", "viewer", None)
        s.commit()


def _login(c, name):
    return c.post("/api/v1/auth/login",
                  json={"username": name, "password": "pw"}).json()["session_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_no_token_401():
    c = TestClient(app)
    r = c.get("/api/v1/models")
    assert r.status_code == 401


def test_viewer_can_read():
    _seed_users()
    c = TestClient(app)
    t = _login(c, "bob_viewer")
    assert c.get("/api/v1/models", headers=_h(t)).status_code == 200
    assert c.get("/api/v1/batches", headers=_h(t)).status_code == 200
    assert c.get("/api/v1/jobs", headers=_h(t)).status_code == 200


def test_viewer_cannot_write():
    _seed_users()
    c = TestClient(app)
    t = _login(c, "bob_viewer")
    r = c.post("/api/v1/models", headers=_h(t),
               json={"name": "m1", "host": "x", "port": 1, "model_name": "m"})
    assert r.status_code == 403


def test_operator_can_write():
    _seed_users()
    c = TestClient(app)
    t = _login(c, "alice_op")
    r = c.post("/api/v1/models", headers=_h(t),
               json={"name": "m1", "host": "x", "port": 1, "model_name": "m"})
    assert r.status_code == 201


def test_operator_cannot_access_users():
    _seed_users()
    c = TestClient(app)
    t = _login(c, "alice_op")
    assert c.get("/api/v1/users", headers=_h(t)).status_code == 403
