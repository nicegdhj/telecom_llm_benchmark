from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, User
from backend.app.services.init_admin import ensure_admin
from backend.app.utils.password import verify_password


def _new_session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'a.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_creates_admin_when_missing(tmp_path):
    s = _new_session(tmp_path)
    ensure_admin(s, username="root", password="secret")
    s.commit()
    u = s.query(User).filter_by(username="root").first()
    assert u is not None
    assert u.role == "admin"
    assert u.is_active is True
    assert verify_password("secret", u.password_hash)


def test_skips_when_admin_exists(tmp_path):
    s = _new_session(tmp_path)
    ensure_admin(s, username="root", password="secret")
    s.commit()
    # 二次调用不会覆盖密码
    ensure_admin(s, username="root", password="otherpass")
    s.commit()
    u = s.query(User).filter_by(username="root").first()
    assert verify_password("secret", u.password_hash)
    assert not verify_password("otherpass", u.password_hash)


def test_noop_when_password_none(tmp_path):
    s = _new_session(tmp_path)
    ensure_admin(s, username="root", password=None)
    s.commit()
    assert s.query(User).count() == 0
