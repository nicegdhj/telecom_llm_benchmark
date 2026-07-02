from datetime import datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, User, UserSession
from backend.app.services.auth_service import (
    login, logout, change_password, resolve_session,
)
from backend.app.utils.password import hash_password


def _session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'as.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def _add_user(s, username="alice", password="pw", role="operator", active=True):
    u = User(username=username, password_hash=hash_password(password),
             role=role, is_active=active)
    s.add(u); s.commit(); s.refresh(u)
    return u


def test_login_ok_creates_session(tmp_path):
    s = _session(tmp_path)
    _add_user(s)
    token, user, expires = login(s, "alice", "pw", ttl_hours=24)
    s.commit()
    assert token and len(token) > 20
    assert user.username == "alice"
    assert expires > datetime.utcnow()
    assert s.query(UserSession).count() == 1
    assert user.last_login_at is not None


def test_login_wrong_password(tmp_path):
    s = _session(tmp_path)
    _add_user(s)
    try:
        login(s, "alice", "WRONG", ttl_hours=24)
        assert False, "should raise"
    except ValueError as e:
        assert "用户名或密码" in str(e)


def test_login_inactive_user(tmp_path):
    s = _session(tmp_path)
    _add_user(s, active=False)
    try:
        login(s, "alice", "pw", ttl_hours=24)
        assert False
    except PermissionError as e:
        assert "停用" in str(e)


def test_resolve_session_ok(tmp_path):
    s = _session(tmp_path)
    _add_user(s)
    token, _, _ = login(s, "alice", "pw", ttl_hours=24)
    s.commit()
    user = resolve_session(s, token)
    assert user.username == "alice"


def test_resolve_session_expired(tmp_path):
    s = _session(tmp_path)
    u = _add_user(s)
    sess = UserSession(token="tok123", user_id=u.id,
                       expires_at=datetime.utcnow() - timedelta(seconds=1))
    s.add(sess); s.commit()
    assert resolve_session(s, "tok123") is None


def test_logout_deletes_session(tmp_path):
    s = _session(tmp_path)
    _add_user(s)
    token, _, _ = login(s, "alice", "pw", ttl_hours=24)
    s.commit()
    logout(s, token)
    s.commit()
    assert s.query(UserSession).count() == 0


def test_change_password_ok(tmp_path):
    s = _session(tmp_path)
    u = _add_user(s)
    change_password(s, u, "pw", "newpw")
    s.commit()
    s.refresh(u)
    from backend.app.utils.password import verify_password
    assert verify_password("newpw", u.password_hash)


def test_change_password_wrong_old(tmp_path):
    s = _session(tmp_path)
    u = _add_user(s)
    try:
        change_password(s, u, "WRONG", "newpw")
        assert False
    except ValueError as e:
        assert "原密码" in str(e)
