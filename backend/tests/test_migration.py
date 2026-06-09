import sqlite3
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app.models import Base, SchemaVersion
from backend.app.services.migration import run_migrations


def _make_engine(tmp_path: Path):
    engine = create_engine(f"sqlite:///{tmp_path/'mig.db'}",
                           connect_args={"check_same_thread": False})
    return engine


def test_migrate_fresh_db_writes_version_2(tmp_path):
    engine = _make_engine(tmp_path)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        run_migrations(s)
        s.commit()
        assert s.query(SchemaVersion).count() == 1
        assert s.query(SchemaVersion).first().version == 4


def test_migrate_idempotent(tmp_path):
    engine = _make_engine(tmp_path)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        run_migrations(s)
        s.commit()
        # 再次执行不应报错也不应增加版本
        run_migrations(s)
        s.commit()
        assert s.query(SchemaVersion).count() == 1
        assert s.query(SchemaVersion).first().version == 4


def test_migrate_old_db_alters_columns(tmp_path):
    """模拟老数据库：手动建一个不含新列的 batches 表，run_migrations 应补上列。"""
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE batches (id INTEGER PRIMARY KEY, name TEXT)")
    conn.execute("CREATE TABLE batch_revisions (id INTEGER PRIMARY KEY, batch_id INTEGER)")
    conn.execute("CREATE TABLE jobs (id INTEGER PRIMARY KEY, type TEXT)")
    conn.commit()
    conn.close()

    engine = create_engine(f"sqlite:///{db_path}",
                           connect_args={"check_same_thread": False})
    # 不调 create_all（模拟旧 schema）
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as s:
        # schema_version 表也得手动建一下（迁移脚本应自己建）
        run_migrations(s)
        s.commit()

    # 验证列已添加
    conn = sqlite3.connect(str(db_path))
    cols = {r[1] for r in conn.execute("PRAGMA table_info(batches)").fetchall()}
    assert "created_by_user_id" in cols
    assert "last_modified_by_user_id" in cols
    cols = {r[1] for r in conn.execute("PRAGMA table_info(batch_revisions)").fetchall()}
    assert "actor_user_id" in cols
    cols = {r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()}
    assert "created_by_user_id" in cols
    conn.close()
