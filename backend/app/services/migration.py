"""SQLite schema 迁移：幂等 ALTER TABLE。

不引入 Alembic。版本管理由 schema_version 表承担。
- v1：旧版本（仅原始 10 张表）
- v2：加入用户/会话表，并给 batches/batch_revisions/jobs 加 user FK
- v3：models.host / models.port 改为可空
- v4：predictions/evaluations/jobs 加 version_label；新增 analysis_views 表；回填历史 version_label
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models import SchemaVersion


CURRENT_VERSION = 4


def _has_table(session: Session, name: str) -> bool:
    row = session.execute(
        text("SELECT name FROM sqlite_master WHERE type='table' AND name=:n"),
        {"n": name},
    ).first()
    return row is not None


def _has_column(session: Session, table: str, column: str) -> bool:
    if not _has_table(session, table):
        return False
    rows = session.execute(text(f"PRAGMA table_info({table})")).fetchall()
    return any(r[1] == column for r in rows)


def _add_column_if_missing(session: Session, table: str, column: str, ddl: str):
    if not _has_table(session, table):
        return
    if _has_column(session, table, column):
        return
    session.execute(text(f"ALTER TABLE {table} ADD COLUMN {ddl}"))


def _read_version(session: Session) -> int:
    if not _has_table(session, "schema_version"):
        return 0
    row = session.query(SchemaVersion).first()
    return row.version if row else 0


def _write_version(session: Session, version: int):
    session.query(SchemaVersion).delete()
    session.add(SchemaVersion(version=version))


def run_migrations(session: Session):
    """幂等迁移。可在每次启动时调用。"""
    if not _has_table(session, "schema_version"):
        session.execute(text("CREATE TABLE IF NOT EXISTS schema_version (version INTEGER PRIMARY KEY)"))

    current = _read_version(session)
    if current >= CURRENT_VERSION:
        return

    # v1 → v2：补 user FK 列（新表 users / user_sessions / schema_version 由 create_all 建）
    _add_column_if_missing(session, "batches", "created_by_user_id",
                           "created_by_user_id INTEGER REFERENCES users(id)")
    _add_column_if_missing(session, "batches", "last_modified_by_user_id",
                           "last_modified_by_user_id INTEGER REFERENCES users(id)")
    _add_column_if_missing(session, "batch_revisions", "actor_user_id",
                           "actor_user_id INTEGER REFERENCES users(id)")
    _add_column_if_missing(session, "jobs", "created_by_user_id",
                           "created_by_user_id INTEGER REFERENCES users(id)")

    # v2 → v3：models.host / models.port 改为可空（支持 common_gateway 等无需 host/port 的配置）
    _migrate_models_host_port_nullable(session)

    # v3 → v4：cell 级版本号 + analysis_views 表
    _add_column_if_missing(session, "predictions", "version_label", "version_label VARCHAR")
    _add_column_if_missing(session, "evaluations", "version_label", "version_label VARCHAR")
    _add_column_if_missing(session, "jobs", "version_label", "version_label VARCHAR")
    _ensure_analysis_views_table(session)
    _backfill_version_labels(session)

    _write_version(session, CURRENT_VERSION)


def _ensure_analysis_views_table(session: Session):
    if _has_table(session, "analysis_views"):
        return
    if not _has_table(session, "users"):
        return  # 老库可能尚未通过 create_all 建 users，此时跳过；后续启动会 create_all 再迁
    session.execute(text("""
        CREATE TABLE analysis_views (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR NOT NULL,
            owner_user_id INTEGER NOT NULL REFERENCES users(id),
            evaluation_ids JSON,
            chart_config JSON,
            created_at DATETIME,
            updated_at DATETIME
        )
    """))


def _backfill_version_labels(session: Session):
    """为历史 Prediction / Evaluation 回填 version_label。

    规则：在同一 cell = (batch_id, model_id, task_id) 范围内，按 created_at 升序
    依次赋 v1, v2, ...。失败的也分配号段，便于追溯。
    Job 的 version_label 沿用其产出的 Prediction/Evaluation 的 label。
    """
    if not (_has_table(session, "predictions") and _has_table(session, "evaluations")
            and _has_table(session, "jobs")):
        return
    # Prediction: 通过 jobs 关联 batch_id
    pred_rows = session.execute(text("""
        SELECT p.id, j.batch_id, p.model_id, p.task_id, p.created_at
        FROM predictions p
        LEFT JOIN jobs j ON j.id = p.job_id
        WHERE p.version_label IS NULL
        ORDER BY j.batch_id, p.model_id, p.task_id, p.created_at, p.id
    """)).fetchall()
    counter: dict[tuple, int] = {}
    for pid, bid, mid, tid, _ in pred_rows:
        key = (bid, mid, tid)
        counter[key] = counter.get(key, 0) + 1
        label = f"v{counter[key]}_infer"
        session.execute(
            text("UPDATE predictions SET version_label=:l WHERE id=:i"),
            {"l": label, "i": pid},
        )
        session.execute(
            text("UPDATE jobs SET version_label=:l WHERE produces_prediction_id=:i"),
            {"l": label, "i": pid},
        )

    # Evaluation: 通过 prediction → job → batch_id
    eval_rows = session.execute(text("""
        SELECT e.id, j.batch_id, p.model_id, p.task_id, e.created_at
        FROM evaluations e
        JOIN predictions p ON p.id = e.prediction_id
        LEFT JOIN jobs j ON j.id = e.job_id
        WHERE e.version_label IS NULL
        ORDER BY j.batch_id, p.model_id, p.task_id, e.created_at, e.id
    """)).fetchall()
    counter = {}
    for eid, bid, mid, tid, _ in eval_rows:
        key = (bid, mid, tid)
        counter[key] = counter.get(key, 0) + 1
        label = f"v{counter[key]}_score"
        session.execute(
            text("UPDATE evaluations SET version_label=:l WHERE id=:i"),
            {"l": label, "i": eid},
        )
        session.execute(
            text("UPDATE jobs SET version_label=:l WHERE produces_evaluation_id=:i"),
            {"l": label, "i": eid},
        )


def _migrate_models_host_port_nullable(session: Session):
    """将 models 表的 host/port 列从 NOT NULL 改为可空（SQLite 需重建表）。"""
    rows = session.execute(text("PRAGMA table_info(models)")).fetchall()
    col_map = {r[1]: r[3] for r in rows}  # name -> notnull
    if not col_map.get("host", 0) and not col_map.get("port", 0):
        return  # 已经是可空，无需迁移

    session.execute(text("""
        CREATE TABLE models_v3 (
            id INTEGER NOT NULL PRIMARY KEY,
            name VARCHAR NOT NULL UNIQUE,
            model_config_key VARCHAR,
            host VARCHAR,
            port INTEGER,
            url TEXT,
            api_key TEXT,
            model_name VARCHAR NOT NULL,
            concurrency INTEGER,
            gen_kwargs_json JSON,
            created_at DATETIME,
            updated_at DATETIME
        )
    """))
    session.execute(text("""
        INSERT INTO models_v3
            (id, name, model_config_key, host, port, url, api_key,
             model_name, concurrency, gen_kwargs_json, created_at, updated_at)
        SELECT id, name, model_config_key, host, port, url, api_key,
               model_name, concurrency, gen_kwargs_json, created_at, updated_at
        FROM models
    """))
    session.execute(text("DROP TABLE models"))
    session.execute(text("ALTER TABLE models_v3 RENAME TO models"))
