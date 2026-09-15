import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, User, UserSession
from backend.app.services.user_service import (
    create_user, update_user, reset_password, deactivate_user,
)
from backend.app.utils.password import hash_password, verify_password


def _session(tmp_path):
    e = create_engine(f"sqlite:///{tmp_path/'us.db'}",
                      connect_args={"check_same_thread": False})
    Base.metadata.create_all(e)
    return sessionmaker(bind=e)()


def _add(s, username, role="operator", active=True):
    u = User(username=username, password_hash=hash_password("x"),
             role=role, is_active=active)
    s.add(u); s.commit(); s.refresh(u)
    return u


def test_create_user_ok(tmp_path):
    s = _session(tmp_path)
    u = create_user(s, username="alice", password="pw", role="operator",
                    display_name="爱丽丝")
    s.commit()
    assert u.id and u.role == "operator"
    assert verify_password("pw", u.password_hash)


def test_create_user_duplicate(tmp_path):
    s = _session(tmp_path)
    create_user(s, "alice", "pw", "operator", None)
    s.commit()
    with pytest.raises(ValueError, match="已存在"):
        create_user(s, "alice", "pw", "viewer", None)


def test_create_user_invalid_role(tmp_path):
    s = _session(tmp_path)
    with pytest.raises(ValueError, match="角色"):
        create_user(s, "x", "pw", "superuser", None)


def test_cannot_demote_last_admin(tmp_path):
    s = _session(tmp_path)
    a = _add(s, "root", "admin")
    with pytest.raises(ValueError, match="最后一个 admin"):
        update_user(s, a, role="viewer")


def test_cannot_deactivate_last_admin(tmp_path):
    s = _session(tmp_path)
    a = _add(s, "root", "admin")
    with pytest.raises(ValueError, match="最后一个 admin"):
        update_user(s, a, is_active=False)


def test_can_demote_when_other_admin_exists(tmp_path):
    s = _session(tmp_path)
    _add(s, "root", "admin")
    a2 = _add(s, "root2", "admin")
    update_user(s, a2, role="operator")
    s.commit()
    assert a2.role == "operator"


def test_admin_cannot_deactivate_self(tmp_path):
    s = _session(tmp_path)
    _add(s, "root", "admin")  # 保证不是最后一个
    a2 = _add(s, "root2", "admin")
    with pytest.raises(ValueError, match="自己"):
        update_user(s, a2, is_active=False, actor_user_id=a2.id)


def test_reset_password(tmp_path):
    s = _session(tmp_path)
    u = _add(s, "alice")
    reset_password(s, u, "newpw")
    s.commit()
    s.refresh(u)
    assert verify_password("newpw", u.password_hash)


def test_deactivate_user_clears_sessions(tmp_path):
    from datetime import datetime, timedelta
    s = _session(tmp_path)
    u = _add(s, "alice")
    s.add(UserSession(token="abc", user_id=u.id,
                      expires_at=datetime.utcnow() + timedelta(hours=1)))
    s.commit()
    deactivate_user(s, u)
    s.commit()
    assert u.is_active is False
    assert s.query(UserSession).count() == 0
