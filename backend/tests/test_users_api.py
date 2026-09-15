from fastapi.testclient import TestClient

from backend.app.db import get_session
from backend.app.main import app
from backend.app.services.user_service import create_user


def _admin_token(c):
    with get_session() as s:
        from backend.app.models import User
        if not s.query(User).filter_by(username="root").first():
            create_user(s, "root", "rootpw", "admin", "管理员")
            s.commit()
    return c.post("/api/v1/auth/login",
                  json={"username": "root", "password": "rootpw"}).json()["session_token"]


def _user_token(c, name="alice", role="operator"):
    with get_session() as s:
        from backend.app.models import User
        if not s.query(User).filter_by(username=name).first():
            create_user(s, name, "pw", role, None)
            s.commit()
    return c.post("/api/v1/auth/login",
                  json={"username": name, "password": "pw"}).json()["session_token"]


def _h(t):
    return {"Authorization": f"Bearer {t}"}


def test_non_admin_cannot_list_users():
    c = TestClient(app)
    t = _user_token(c, "alice", "operator")
    r = c.get("/api/v1/users", headers=_h(t))
    assert r.status_code == 403


def test_admin_can_list_users():
    c = TestClient(app)
    t = _admin_token(c)
    r = c.get("/api/v1/users", headers=_h(t))
    assert r.status_code == 200
    assert any(u["username"] == "root" for u in r.json())


def test_admin_can_create_user():
    c = TestClient(app)
    t = _admin_token(c)
    r = c.post("/api/v1/users", headers=_h(t),
               json={"username": "bob", "password": "pw",
                     "role": "viewer", "display_name": "Bob"})
    assert r.status_code == 201
    assert r.json()["username"] == "bob"


def test_create_user_duplicate_400():
    c = TestClient(app)
    t = _admin_token(c)
    c.post("/api/v1/users", headers=_h(t),
           json={"username": "bob", "password": "pw", "role": "viewer"})
    r = c.post("/api/v1/users", headers=_h(t),
               json={"username": "bob", "password": "pw", "role": "viewer"})
    assert r.status_code == 400
    assert "已存在" in r.json()["detail"]


def test_cannot_demote_last_admin():
    c = TestClient(app)
    t = _admin_token(c)
    me = c.get("/api/v1/auth/me", headers=_h(t)).json()
    r = c.put(f"/api/v1/users/{me['id']}", headers=_h(t),
              json={"role": "viewer"})
    assert r.status_code == 400


def test_admin_cannot_deactivate_self():
    c = TestClient(app)
    t = _admin_token(c)
    # 多建一个 admin，避免命中"最后一个 admin"提前拦截
    c.post("/api/v1/users", headers=_h(t),
           json={"username": "admin2", "password": "pw", "role": "admin"})
    me = c.get("/api/v1/auth/me", headers=_h(t)).json()
    r = c.delete(f"/api/v1/users/{me['id']}", headers=_h(t))
    assert r.status_code == 400
    assert "自己" in r.json()["detail"]


def test_reset_password():
    c = TestClient(app)
    t = _admin_token(c)
    c.post("/api/v1/users", headers=_h(t),
           json={"username": "resetme", "password": "old", "role": "viewer"})
    uid = [u for u in c.get("/api/v1/users", headers=_h(t)).json()
           if u["username"] == "resetme"][0]["id"]
    r = c.post(f"/api/v1/users/{uid}/reset-password", headers=_h(t),
               json={"new_password": "new"})
    assert r.status_code == 204
    # 用新密码登录
    r = c.post("/api/v1/auth/login",
               json={"username": "resetme", "password": "new"})
    assert r.status_code == 200


def test_update_user():
    c = TestClient(app)
    t = _admin_token(c)
    c.post("/api/v1/users", headers=_h(t),
           json={"username": "upme", "password": "pw", "role": "viewer"})
    uid = [u for u in c.get("/api/v1/users", headers=_h(t)).json()
           if u["username"] == "upme"][0]["id"]
    r = c.put(f"/api/v1/users/{uid}", headers=_h(t),
              json={"display_name": "Updated", "role": "operator"})
    assert r.status_code == 200
    assert r.json()["display_name"] == "Updated"
    assert r.json()["role"] == "operator"
