from fastapi.testclient import TestClient

from backend.app.db import get_session
from backend.app.main import app
from backend.app.services.user_service import create_user


def _seed(username="alice", password="pw", role="operator"):
    with get_session() as s:
        create_user(s, username, password, role, None)
        s.commit()


def test_login_ok():
    _seed()
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"username": "alice", "password": "pw"})
    assert r.status_code == 200
    body = r.json()
    assert body["session_token"]
    assert body["user"]["username"] == "alice"
    assert body["user"]["role"] == "operator"


def test_login_wrong_password():
    _seed()
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"username": "alice", "password": "WRONG"})
    assert r.status_code == 401


def test_login_unknown_user():
    c = TestClient(app)
    r = c.post("/api/v1/auth/login", json={"username": "ghost", "password": "x"})
    assert r.status_code == 401


def test_me_ok():
    _seed()
    c = TestClient(app)
    token = c.post("/api/v1/auth/login",
                   json={"username": "alice", "password": "pw"}).json()["session_token"]
    r = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 200
    assert r.json()["username"] == "alice"


def test_me_no_token():
    c = TestClient(app)
    r = c.get("/api/v1/auth/me")
    assert r.status_code == 401


def test_logout_then_me_401():
    _seed()
    c = TestClient(app)
    token = c.post("/api/v1/auth/login",
                   json={"username": "alice", "password": "pw"}).json()["session_token"]
    r = c.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 204
    r = c.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 401


def test_change_password_then_relogin():
    _seed()
    c = TestClient(app)
    token = c.post("/api/v1/auth/login",
                   json={"username": "alice", "password": "pw"}).json()["session_token"]
    r = c.post("/api/v1/auth/change-password",
               headers={"Authorization": f"Bearer {token}"},
               json={"old_password": "pw", "new_password": "newpw"})
    assert r.status_code == 204
    # 旧密码失败
    r = c.post("/api/v1/auth/login", json={"username": "alice", "password": "pw"})
    assert r.status_code == 401
    # 新密码成功
    r = c.post("/api/v1/auth/login", json={"username": "alice", "password": "newpw"})
    assert r.status_code == 200


def test_system_token_bypass(monkeypatch):
    monkeypatch.setenv("EVAL_BACKEND_AUTH_TOKEN", "magic")
    from backend.app.config import get_settings
    get_settings.cache_clear()

    c = TestClient(app)
    r = c.get("/api/v1/auth/me", headers={"Authorization": "Bearer magic"})
    assert r.status_code == 200
    assert r.json()["username"] == "__system__"
    assert r.json()["role"] == "admin"
