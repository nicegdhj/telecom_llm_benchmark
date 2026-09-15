import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import db as db_mod
from backend.app.config import get_settings
from backend.app.main import app
from backend.app.models import Base


@pytest.fixture(autouse=True)
def _fresh_db(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}",
                           connect_args={"check_same_thread": False})
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)
    monkeypatch.setattr(db_mod, "_engine", engine)
    monkeypatch.setattr(db_mod, "_SessionLocal", SessionLocal)
    monkeypatch.setenv("EVAL_BACKEND_WORKSPACE_DIR", str(tmp_path / "workspace"))
    # 默认开启 system token bypass，让旧业务测试免登录
    monkeypatch.setenv("EVAL_BACKEND_AUTH_TOKEN", "test-system-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def client():
    """返回带 system token 头的 TestClient（旧业务测试用）。"""
    c = TestClient(app)
    c.headers.update({"Authorization": "Bearer test-system-token"})
    return c


@pytest.fixture
def raw_client():
    """无 token 的 TestClient（auth/users/rbac 测试用）。"""
    return TestClient(app)
