from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session

from backend.app.config import get_settings
from backend.app.models import Base


_engine = None
_SessionLocal = None


def init_db():
    global _engine, _SessionLocal
    settings = get_settings()
    settings.backend_data_dir.mkdir(parents=True, exist_ok=True)
    _engine = create_engine(
        f"sqlite:///{settings.db_path}",
        connect_args={"check_same_thread": False},
    )
    _SessionLocal = sessionmaker(bind=_engine, autocommit=False, autoflush=False)
    Base.metadata.create_all(_engine)
    # 增量迁移：为旧版本 DB 补齐新列（已存在时 SQLite 会报错，直接忽略）
    with _engine.connect() as conn:
        for stmt in [
            "ALTER TABLE models ADD COLUMN url TEXT",
            "ALTER TABLE models ADD COLUMN api_key TEXT",
            "ALTER TABLE judges ADD COLUMN judge_config_key TEXT DEFAULT 'local_judge'",
            "ALTER TABLE judges ADD COLUMN url TEXT",
            "ALTER TABLE judges ADD COLUMN api_key TEXT",
            "ALTER TABLE judges ADD COLUMN score_model_type TEXT DEFAULT 'maas'",
            "ALTER TABLE judges ADD COLUMN concurrency INTEGER DEFAULT 5",
        ]:
            try:
                conn.execute(__import__("sqlalchemy").text(stmt))
                conn.commit()
            except Exception:
                pass

    # 权限系统：迁移 + admin 初始化 + 任务/init 版本幂等种植
    from backend.app.services.migration import run_migrations
    from backend.app.services.init_admin import ensure_admin
    from backend.app.services.seed import (
        seed_generic_tasks, seed_custom_tasks, seed_init_versions,
        DEFAULT_GENERIC, DEFAULT_CUSTOM,
    )

    with _SessionLocal() as session:
        run_migrations(session)
        ensure_admin(session, settings.admin_username, settings.admin_password)
        # 幂等种植：补齐任务行、回填数据路径、挂载 init 版本，
        # 使任何全新部署（docker/local）首启即得到一致的单库状态。
        seed_generic_tasks(session, DEFAULT_GENERIC)
        seed_custom_tasks(session, DEFAULT_CUSTOM)
        session.flush()  # 确保新建 task.id 可用，供挂载 init 版本
        seed_init_versions(session)
        session.commit()


@contextmanager
def get_session():
    """带 rollback 保障的 session 上下文管理器。异常时自动回滚。"""
    if _SessionLocal is None:
        init_db()
    session = _SessionLocal()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
