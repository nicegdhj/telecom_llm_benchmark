# 权限管理系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在现有 FastAPI + React 评测平台上，新增最小可用的多用户登录、三角色 RBAC（admin / operator / viewer）、和"操作人"显示。

**Architecture:** 不引入 JWT/Alembic；用 SQLite 存 `users` + `user_sessions` 表（随机字符串 session）；鉴权移到 FastAPI 依赖注入层；前端复用现有 Bearer 头机制；操作人字段加在 Batch / BatchRevision / Job 三张表。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.x, SQLite, passlib[bcrypt], React 18, zustand, react-router-dom, lucide-react

**Spec:** `docs/superpowers/specs/2026-04-23-permission-system-design.md`

---

## 文件结构

### 后端（新增 / 修改）

| 文件 | 操作 | 责任 |
|------|------|------|
| `backend/pyproject.toml` | 修改 | 加 passlib[bcrypt] 依赖 |
| `backend/app/config.py` | 修改 | 加 admin_username / admin_password / session_ttl_hours / session_cleanup_interval_sec |
| `backend/app/models.py` | 修改 | 新增 User / UserSession / SchemaVersion；现有 Batch / BatchRevision / Job 加 user FK 字段 |
| `backend/app/utils/__init__.py` | 新增 | utils 包占位 |
| `backend/app/utils/password.py` | 新增 | bcrypt 包装 |
| `backend/app/services/migration.py` | 新增 | schema_version 与 ALTER TABLE 幂等迁移 |
| `backend/app/services/init_admin.py` | 新增 | 启动时初始化 admin |
| `backend/app/services/auth_service.py` | 新增 | login / logout / change_password / 解析 token |
| `backend/app/services/user_service.py` | 新增 | 用户 CRUD + 业务约束（最后 admin 等） |
| `backend/app/services/session_cleanup.py` | 新增 | 后台协程清理过期 session |
| `backend/app/services/batch_service.py` | 修改 | create_batch / rerun_batch 接收 actor 参数 |
| `backend/app/db.py` | 修改 | init_db 末尾调迁移 + admin 初始化 |
| `backend/app/deps.py` | 修改 | 新增 current_user / require_role；删除旧 verify_token |
| `backend/app/main.py` | 修改 | 删除 _auth_middleware；挂载 auth/users router；启动 session 清理协程 |
| `backend/app/schemas.py` | 修改 | 加 UserBrief / UserOut / UserCreate / UserUpdate / LoginIn / LoginOut / ChangePasswordIn 等；扩展 BatchOut / JobOut |
| `backend/app/routers/auth.py` | 新增 | /auth/login, /logout, /me, /change-password |
| `backend/app/routers/users.py` | 新增 | /users CRUD + reset-password |
| `backend/app/routers/batches.py` | 修改 | 加 RBAC 依赖；create / rerun 把 current_user 传给 service |
| `backend/app/routers/jobs.py` | 修改 | 加 RBAC 依赖 |
| `backend/app/routers/models.py` | 修改 | 加 RBAC 依赖 |
| `backend/app/routers/judges.py` | 修改 | 加 RBAC 依赖 |
| `backend/app/routers/tasks.py` | 修改 | 加 RBAC 依赖 |
| `backend/app/routers/predictions.py` | 修改 | 加 RBAC 依赖 |
| `backend/app/routers/evaluations.py` | 修改 | 加 RBAC 依赖 |
| `backend/tests/conftest.py` | 修改 | 加 admin/operator/viewer fixture + auth_client helper |
| `backend/tests/test_password.py` | 新增 | 哈希/校验 |
| `backend/tests/test_migration.py` | 新增 | 迁移幂等 |
| `backend/tests/test_auth_api.py` | 新增 | login/logout/me/change-password |
| `backend/tests/test_users_api.py` | 新增 | 用户 CRUD + 业务约束 |
| `backend/tests/test_rbac.py` | 新增 | 各角色对各端点的 200/401/403 矩阵抽样 |
| `backend/tests/test_batch_actor.py` | 新增 | 创建/rerun batch 时 actor 字段被正确填充 |

### 前端（新增 / 修改）

| 文件 | 操作 | 责任 |
|------|------|------|
| `frontend/src/store/authStore.js` | 修改 | 加 user 字段 / setSession / clearSession / isAdmin / canWrite |
| `frontend/src/lib/api.js` | 修改 | 加 auth、users 分组；request 401 自动跳登录 |
| `frontend/src/lib/userDisplay.js` | 新增 | 用户显示规则 |
| `frontend/src/components/auth/RequireAuth.jsx` | 新增 | 路由守卫 |
| `frontend/src/components/auth/RequireAdmin.jsx` | 新增 | admin 路由守卫 |
| `frontend/src/components/ui/RoleButton.jsx` | 新增 | 角色门禁按钮 |
| `frontend/src/components/layout/Sidebar.jsx` | 修改 | 用户卡片 + 用户管理入口（admin 可见） + 退出 |
| `frontend/src/pages/LoginPage.jsx` | 新增 | 登录页 |
| `frontend/src/pages/SettingsPage.jsx` | 修改 | 删 token 卡片，加修改密码卡片 |
| `frontend/src/features/users/UsersPage.jsx` | 新增 | 用户列表 |
| `frontend/src/features/users/components/UserFormModal.jsx` | 新增 | 新增 / 编辑用户 |
| `frontend/src/features/users/components/ResetPasswordModal.jsx` | 新增 | 重置密码 |
| `frontend/src/features/batches/BatchDetailPage.jsx` | 修改 | 头部显示 创建人 / 最后修改人 |
| `frontend/src/features/jobs/JobsPage.jsx` | 修改 | 列表加"提交人"列 |
| `frontend/src/App.jsx` | 修改 | 加 /login 路由 + RequireAuth 包装 + /users 路由 |

---

## Task 1：加 passlib 依赖、扩展 config

**Files:**
- Modify: `backend/pyproject.toml`
- Modify: `backend/app/config.py`

- [ ] **Step 1：在 `backend/pyproject.toml` dependencies 中加 passlib**

把第 5-13 行的 `dependencies` 改为：

```toml
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "pydantic>=2.8",
    "pydantic-settings>=2.4",
    "pyyaml>=6.0",
    "python-multipart>=0.0.9",
    "passlib[bcrypt]>=1.7.4",
]
```

- [ ] **Step 2：安装新依赖**

```bash
cd backend && pip install -e ".[dev]"
```

预期：成功安装 passlib 与 bcrypt。

- [ ] **Step 3：扩展 `backend/app/config.py`**

把 `class Settings(BaseSettings):` 块替换为：

```python
class Settings(BaseSettings):
    backend_data_dir: Path = Path("./backend_data")
    workspace_dir: Path = Path("/opt/eval_workspace")
    code_dir: Path = Path("/opt/eval_workspace/code")
    docker_image_tag: str = "benchmark-eval:latest"
    worker_poll_interval_sec: float = 1.0
    default_job_concurrency: int = 4
    auth_token: str | None = None

    # 权限系统新增
    admin_username: str = "admin"
    admin_password: str | None = None        # 仅首次启动时初始化使用
    session_ttl_hours: int = 168             # 7 天
    session_cleanup_interval_sec: int = 3600 # 每小时清理一次
```

- [ ] **Step 4：commit**

```bash
git add backend/pyproject.toml backend/app/config.py
git commit -m "feat(backend): 加 passlib 依赖与权限相关配置项"
```

---

## Task 2：写密码哈希工具 + 测试

**Files:**
- Create: `backend/app/utils/__init__.py`
- Create: `backend/app/utils/password.py`
- Create: `backend/tests/test_password.py`

- [ ] **Step 1：先写失败测试 `backend/tests/test_password.py`**

```python
from backend.app.utils.password import hash_password, verify_password


def test_hash_then_verify_ok():
    h = hash_password("hello123")
    assert h != "hello123"
    assert verify_password("hello123", h) is True


def test_hash_then_verify_wrong():
    h = hash_password("hello123")
    assert verify_password("wrong", h) is False


def test_hash_two_calls_differ():
    """同一密码两次 hash 结果不同（每次 salt 随机）。"""
    assert hash_password("x") != hash_password("x")
```

- [ ] **Step 2：跑测试，确认失败**

```bash
cd backend && pytest tests/test_password.py -v
```

预期：FAIL（模块不存在）。

- [ ] **Step 3：建包**

```bash
touch backend/app/utils/__init__.py
```

- [ ] **Step 4：实现 `backend/app/utils/password.py`**

```python
from passlib.context import CryptContext

_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(plain: str) -> str:
    return _pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    if not hashed:
        return False
    try:
        return _pwd_context.verify(plain, hashed)
    except Exception:
        return False
```

- [ ] **Step 5：跑测试，确认通过**

```bash
cd backend && pytest tests/test_password.py -v
```

预期：PASS（3 个用例）。

- [ ] **Step 6：commit**

```bash
git add backend/app/utils/ backend/tests/test_password.py
git commit -m "feat(backend): 加 bcrypt 密码哈希工具"
```

---

## Task 3：扩展数据模型（User / UserSession / SchemaVersion + 三表加列）

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1：在 `backend/app/models.py` 末尾追加新模型**

打开 `backend/app/models.py`，在文件**末尾**追加：

```python
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(String, nullable=False)  # admin | operator | viewer
    display_name = Column(String)
    is_active = Column(Boolean, default=True, nullable=False)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class UserSession(Base):
    __tablename__ = "user_sessions"
    id = Column(Integer, primary_key=True)
    token = Column(String, unique=True, nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    created_at = Column(DateTime, default=_now)
    last_used_at = Column(DateTime, default=_now)
    expires_at = Column(DateTime, nullable=False)


class SchemaVersion(Base):
    __tablename__ = "schema_version"
    version = Column(Integer, primary_key=True)
```

- [ ] **Step 2：给 `Batch` 加两个字段**

定位 `class Batch(Base):` 块（约第 104 行起），在 `notes = Column(Text)` 行**之前**插入：

```python
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
    last_modified_by_user_id = Column(Integer, ForeignKey("users.id"))
```

并在 class 末尾（`updated_at` 之后）追加 relationships，便于 Pydantic from_attributes：

```python
    created_by = relationship("User", foreign_keys=[created_by_user_id])
    last_modified_by = relationship("User", foreign_keys=[last_modified_by_user_id])
```

- [ ] **Step 3：给 `BatchRevision` 加字段**

在 `class BatchRevision(Base):` 中，在 `created_at` 之前插入：

```python
    actor_user_id = Column(Integer, ForeignKey("users.id"))
```

- [ ] **Step 4：给 `Job` 加字段 + relationship**

在 `class Job(Base):` 的 `created_at` 之前插入：

```python
    created_by_user_id = Column(Integer, ForeignKey("users.id"))
```

并在 class 末尾追加：

```python
    created_by = relationship("User", foreign_keys=[created_by_user_id])
```

- [ ] **Step 5：跑现有测试确认未破坏**

```bash
cd backend && pytest tests/ -v -x
```

预期：所有原测试仍通过（新表 / 新列对旧业务无副作用，conftest 用 `Base.metadata.create_all` 会自动建新表）。

- [ ] **Step 6：commit**

```bash
git add backend/app/models.py
git commit -m "feat(backend): 加 User/UserSession/SchemaVersion 模型，Batch/BatchRevision/Job 加 user FK"
```

---

## Task 4：迁移脚本（schema_version + ALTER TABLE 幂等）

**Files:**
- Create: `backend/app/services/migration.py`
- Create: `backend/tests/test_migration.py`

- [ ] **Step 1：写失败测试 `backend/tests/test_migration.py`**

```python
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
        assert s.query(SchemaVersion).first().version == 2


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
        assert s.query(SchemaVersion).first().version == 2


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
```

- [ ] **Step 2：跑测试，确认失败**

```bash
cd backend && pytest tests/test_migration.py -v
```

预期：FAIL（migration 模块不存在）。

- [ ] **Step 3：实现 `backend/app/services/migration.py`**

```python
"""SQLite schema 迁移：幂等 ALTER TABLE。

不引入 Alembic。版本管理由 schema_version 表承担。
- v1：旧版本（仅原始 10 张表）
- v2：加入用户/会话表，并给 batches/batch_revisions/jobs 加 user FK
"""
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.models import SchemaVersion


CURRENT_VERSION = 2


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

    _write_version(session, CURRENT_VERSION)
```

- [ ] **Step 4：跑测试，确认通过**

```bash
cd backend && pytest tests/test_migration.py -v
```

预期：3 个用例 PASS。

- [ ] **Step 5：commit**

```bash
git add backend/app/services/migration.py backend/tests/test_migration.py
git commit -m "feat(backend): 加幂等 schema 迁移脚本（v1 → v2）"
```

---

## Task 5：admin 初始化逻辑

**Files:**
- Create: `backend/app/services/init_admin.py`
- Create: `backend/tests/test_init_admin.py`

- [ ] **Step 1：写失败测试 `backend/tests/test_init_admin.py`**

```python
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
```

- [ ] **Step 2：跑测试，确认失败**

```bash
cd backend && pytest tests/test_init_admin.py -v
```

- [ ] **Step 3：实现 `backend/app/services/init_admin.py`**

```python
from sqlalchemy.orm import Session

from backend.app.models import User
from backend.app.utils.password import hash_password


def ensure_admin(session: Session, username: str, password: str | None):
    """启动时调用：确保至少存在一个 admin。
    若 password 为 None：什么都不做（部署者未设环境变量）。
    若该 username 已存在：跳过（DB 为准，不覆盖密码）。
    否则创建一个 admin 用户。
    """
    if not password:
        return
    existing = session.query(User).filter_by(username=username).first()
    if existing:
        return
    session.add(User(
        username=username,
        password_hash=hash_password(password),
        role="admin",
        display_name="超级管理员",
        is_active=True,
    ))
```

- [ ] **Step 4：跑测试，确认通过**

```bash
cd backend && pytest tests/test_init_admin.py -v
```

- [ ] **Step 5：commit**

```bash
git add backend/app/services/init_admin.py backend/tests/test_init_admin.py
git commit -m "feat(backend): 加 ensure_admin 启动初始化逻辑"
```

---

## Task 6：把迁移与 admin 初始化接入 init_db

**Files:**
- Modify: `backend/app/db.py`

- [ ] **Step 1：替换 `backend/app/db.py` 的 `init_db` 函数**

把 `init_db()` 改为：

```python
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

    # 权限系统：迁移 + admin 初始化
    from backend.app.services.migration import run_migrations
    from backend.app.services.init_admin import ensure_admin

    with _SessionLocal() as session:
        run_migrations(session)
        ensure_admin(session, settings.admin_username, settings.admin_password)
        session.commit()
```

- [ ] **Step 2：跑现有所有测试，确认未破坏**

```bash
cd backend && pytest tests/ -v -x
```

预期：所有测试仍通过。

- [ ] **Step 3：commit**

```bash
git add backend/app/db.py
git commit -m "feat(backend): init_db 末尾接入迁移与 admin 初始化"
```

---

## Task 7：auth_service（登录/会话/改密 业务逻辑）+ 测试

**Files:**
- Create: `backend/app/services/auth_service.py`
- Create: `backend/tests/test_auth_service.py`

- [ ] **Step 1：写失败测试 `backend/tests/test_auth_service.py`**

```python
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
```

- [ ] **Step 2：跑测试，确认失败**

```bash
cd backend && pytest tests/test_auth_service.py -v
```

- [ ] **Step 3：实现 `backend/app/services/auth_service.py`**

```python
import secrets
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.models import User, UserSession
from backend.app.utils.password import hash_password, verify_password


def login(session: Session, username: str, password: str, ttl_hours: int):
    """成功返回 (token, user, expires_at)。失败抛 ValueError / PermissionError。"""
    user = session.query(User).filter_by(username=username).first()
    if not user or not verify_password(password, user.password_hash):
        raise ValueError("用户名或密码错误")
    if not user.is_active:
        raise PermissionError("账号已停用")

    token = secrets.token_urlsafe(32)
    expires_at = datetime.utcnow() + timedelta(hours=ttl_hours)
    sess = UserSession(token=token, user_id=user.id, expires_at=expires_at)
    user.last_login_at = datetime.utcnow()
    session.add(sess)
    return token, user, expires_at


def logout(session: Session, token: str):
    """删除指定 session。token 不存在则静默忽略。"""
    sess = session.query(UserSession).filter_by(token=token).first()
    if sess:
        session.delete(sess)


def logout_all_for_user(session: Session, user_id: int):
    """删除某用户所有 session（停用/删除用户时使用）。"""
    session.query(UserSession).filter_by(user_id=user_id).delete()


def resolve_session(session: Session, token: str) -> User | None:
    """根据 token 找用户。过期 / 不存在 / 用户停用 → 返回 None。"""
    sess = session.query(UserSession).filter_by(token=token).first()
    if not sess:
        return None
    if sess.expires_at < datetime.utcnow():
        return None
    user = session.get(User, sess.user_id)
    if not user or not user.is_active:
        return None
    sess.last_used_at = datetime.utcnow()
    return user


def change_password(session: Session, user: User, old: str, new: str):
    if not verify_password(old, user.password_hash):
        raise ValueError("原密码错误")
    user.password_hash = hash_password(new)


def cleanup_expired_sessions(session: Session) -> int:
    """删除所有过期 session，返回删除条数。"""
    n = session.query(UserSession).filter(
        UserSession.expires_at < datetime.utcnow()
    ).delete()
    return n
```

- [ ] **Step 4：跑测试，确认通过**

```bash
cd backend && pytest tests/test_auth_service.py -v
```

预期：8 个用例 PASS。

- [ ] **Step 5：commit**

```bash
git add backend/app/services/auth_service.py backend/tests/test_auth_service.py
git commit -m "feat(backend): 加 auth_service（login/logout/resolve/change_password）"
```

---

## Task 8：user_service（用户 CRUD + 业务约束）+ 测试

**Files:**
- Create: `backend/app/services/user_service.py`
- Create: `backend/tests/test_user_service.py`

- [ ] **Step 1：写失败测试 `backend/tests/test_user_service.py`**

```python
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
```

- [ ] **Step 2：跑测试，确认失败**

```bash
cd backend && pytest tests/test_user_service.py -v
```

- [ ] **Step 3：实现 `backend/app/services/user_service.py`**

```python
from sqlalchemy.orm import Session

from backend.app.models import User
from backend.app.services.auth_service import logout_all_for_user
from backend.app.utils.password import hash_password


VALID_ROLES = {"admin", "operator", "viewer"}


def _count_active_admins(session: Session) -> int:
    return session.query(User).filter_by(role="admin", is_active=True).count()


def create_user(session: Session, username: str, password: str,
                role: str, display_name: str | None) -> User:
    if role not in VALID_ROLES:
        raise ValueError(f"非法角色：{role}（允许：{sorted(VALID_ROLES)}）")
    if session.query(User).filter_by(username=username).first():
        raise ValueError(f"用户名 {username!r} 已存在")
    u = User(
        username=username,
        password_hash=hash_password(password),
        role=role,
        display_name=display_name,
        is_active=True,
    )
    session.add(u)
    session.flush()
    return u


def update_user(session: Session, user: User, *,
                role: str | None = None,
                display_name: str | None = None,
                is_active: bool | None = None,
                actor_user_id: int | None = None) -> User:
    """部分更新用户属性，附带业务约束校验。"""
    # 角色变更：不允许把唯一 active admin 降级
    if role is not None:
        if role not in VALID_ROLES:
            raise ValueError(f"非法角色：{role}")
        if (user.role == "admin" and role != "admin"
                and _count_active_admins(session) <= 1):
            raise ValueError("不能降级最后一个 admin")
        user.role = role

    # 停用：不允许停用唯一 active admin；不允许停用自己
    if is_active is not None:
        if is_active is False:
            if actor_user_id is not None and actor_user_id == user.id:
                raise ValueError("不能停用/删除自己")
            if user.role == "admin" and _count_active_admins(session) <= 1:
                raise ValueError("不能停用最后一个 admin")
        user.is_active = is_active
        if is_active is False:
            logout_all_for_user(session, user.id)

    if display_name is not None:
        user.display_name = display_name

    return user


def reset_password(session: Session, user: User, new_password: str):
    user.password_hash = hash_password(new_password)


def deactivate_user(session: Session, user: User, actor_user_id: int | None = None):
    """等价于 update_user(is_active=False)。"""
    update_user(session, user, is_active=False, actor_user_id=actor_user_id)
```

- [ ] **Step 4：跑测试，确认通过**

```bash
cd backend && pytest tests/test_user_service.py -v
```

预期：9 个用例 PASS。

- [ ] **Step 5：commit**

```bash
git add backend/app/services/user_service.py backend/tests/test_user_service.py
git commit -m "feat(backend): 加 user_service（CRUD + 业务约束）"
```

---

## Task 9：current_user / require_role 依赖（替换旧 verify_token）

**Files:**
- Modify: `backend/app/deps.py`

- [ ] **Step 1：替换 `backend/app/deps.py` 完整内容**

```python
from typing import Generator, Iterable

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db import init_db
from backend.app.models import User
from backend.app.services.auth_service import resolve_session


# 虚拟 system admin（来自旧 EVAL_BACKEND_AUTH_TOKEN bypass，不入 DB）
_SYSTEM_USER = User(
    id=None,
    username="__system__",
    password_hash="",
    role="admin",
    display_name="系统",
    is_active=True,
)


def db_session() -> Generator[Session, None, None]:
    """FastAPI 依赖注入：自动 commit，异常自动 rollback。"""
    from backend.app.db import _SessionLocal

    if _SessionLocal is None:
        init_db()
    session = _SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def current_user(authorization: str | None = Header(None),
                 db: Session = Depends(db_session)) -> User:
    """解析 Bearer token → User。无效则 401，停用则 403。"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "未登录")
    token = authorization[len("Bearer "):]

    settings = get_settings()
    # 旧 EVAL_BACKEND_AUTH_TOKEN bypass
    if settings.auth_token and token == settings.auth_token:
        return _SYSTEM_USER

    user = resolve_session(db, token)
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "会话无效或已过期")
    return user


def require_role(*allowed_roles: str):
    """依赖工厂：require_role('admin') / require_role('admin','operator')。"""
    allowed = set(allowed_roles)

    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "权限不足")
        return user

    return dep
```

- [ ] **Step 2：跑现有测试**

```bash
cd backend && pytest tests/ -v -x
```

预期：原本未鉴权的测试仍通过；本步骤不应引入失败（旧 `verify_token` 引用还未被删除，但也未被任何 router 强制使用）。

> 注：`verify_token` 函数已不存在。如果有测试或代码 import 了它，需在后续 task 中处理。grep 检查：

```bash
grep -rn "verify_token" backend/
```

如果有引用，留待 Task 12 统一处理。

- [ ] **Step 3：commit**

```bash
git add backend/app/deps.py
git commit -m "feat(backend): 替换 verify_token，加 current_user/require_role 依赖"
```

---

## Task 10：auth router（登录 / 退出 / me / 改密）+ 测试

**Files:**
- Create: `backend/app/routers/auth.py`
- Create: `backend/tests/test_auth_api.py`
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1：在 `backend/app/schemas.py` 末尾追加 schema**

```python
class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int | None
    username: str
    display_name: str | None
    role: str
    is_active: bool


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    display_name: str | None
    role: str
    is_active: bool
    last_login_at: datetime | None
    created_at: datetime
    updated_at: datetime


class LoginIn(BaseModel):
    username: str
    password: str


class LoginOut(BaseModel):
    session_token: str
    expires_at: datetime
    user: UserBrief


class ChangePasswordIn(BaseModel):
    old_password: str
    new_password: str = Field(..., min_length=1)


class UserCreate(BaseModel):
    username: str
    password: str = Field(..., min_length=1)
    role: str
    display_name: str | None = None


class UserUpdate(BaseModel):
    role: str | None = None
    display_name: str | None = None
    is_active: bool | None = None


class ResetPasswordIn(BaseModel):
    new_password: str = Field(..., min_length=1)
```

- [ ] **Step 2：实现 `backend/app/routers/auth.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, Header, status
from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.deps import current_user, db_session
from backend.app.models import User
from backend.app.schemas import (
    ChangePasswordIn, LoginIn, LoginOut, UserBrief,
)
from backend.app.services import auth_service


router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


@router.post("/login", response_model=LoginOut)
def login(payload: LoginIn, db: Session = Depends(db_session)):
    settings = get_settings()
    try:
        token, user, expires = auth_service.login(
            db, payload.username, payload.password,
            ttl_hours=settings.session_ttl_hours,
        )
    except ValueError as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e))
    except PermissionError as e:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(e))
    return LoginOut(
        session_token=token,
        expires_at=expires,
        user=UserBrief.model_validate(user),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout(authorization: str | None = Header(None),
           _: User = Depends(current_user),
           db: Session = Depends(db_session)):
    if authorization and authorization.startswith("Bearer "):
        auth_service.logout(db, authorization[len("Bearer "):])
    return None


@router.get("/me", response_model=UserBrief)
def me(user: User = Depends(current_user)):
    return UserBrief.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
def change_password(payload: ChangePasswordIn,
                    user: User = Depends(current_user),
                    db: Session = Depends(db_session)):
    if user.id is None:
        # __system__ 用户不能改密
        raise HTTPException(403, "系统账号不支持修改密码")
    try:
        auth_service.change_password(db, user, payload.old_password, payload.new_password)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return None
```

- [ ] **Step 3：在 `backend/app/main.py` 中挂载路由 + 删 _auth_middleware**

打开 `backend/app/main.py`，替换为：

```python
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.db import init_db
from backend.app.routers import auth as auth_router
from backend.app.routers import batches as batches_router
from backend.app.routers import evaluations as evaluations_router
from backend.app.routers import judges as judges_router
from backend.app.routers import jobs as jobs_router
from backend.app.routers import models as models_router
from backend.app.routers import predictions as predictions_router
from backend.app.routers import tasks as tasks_router
from backend.app.services.worker import worker_loop


_worker_task = None
_session_cleanup_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task, _session_cleanup_task
    init_db()
    _worker_task = asyncio.create_task(worker_loop())
    # session 清理协程在 Task 14 中加入；此处先留占位
    yield
    if _worker_task:
        _worker_task.cancel()
    if _session_cleanup_task:
        _session_cleanup_task.cancel()


app = FastAPI(title="Eval Backend", version="0.2.0", lifespan=lifespan)
app.include_router(auth_router.router)
app.include_router(models_router.router)
app.include_router(judges_router.router)
app.include_router(tasks_router.router)
app.include_router(batches_router.router)
app.include_router(jobs_router.router)
app.include_router(predictions_router.router)
app.include_router(evaluations_router.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
```

> users router 在 Task 11 加入。

- [ ] **Step 4：写 `backend/tests/test_auth_api.py`**

```python
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
```

- [ ] **Step 5：跑测试，确认通过**

```bash
cd backend && pytest tests/test_auth_api.py -v
```

预期：8 个用例 PASS。

- [ ] **Step 6：commit**

```bash
git add backend/app/routers/auth.py backend/app/schemas.py backend/app/main.py backend/tests/test_auth_api.py
git commit -m "feat(backend): 加 /auth router（login/logout/me/change-password）"
```

---

## Task 11：users router（admin 管理用户）+ 测试

**Files:**
- Create: `backend/app/routers/users.py`
- Create: `backend/tests/test_users_api.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1：实现 `backend/app/routers/users.py`**

```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.deps import db_session, require_role
from backend.app.models import User
from backend.app.schemas import (
    ResetPasswordIn, UserCreate, UserOut, UserUpdate,
)
from backend.app.services import user_service


router = APIRouter(prefix="/api/v1/users", tags=["users"])


@router.get("", response_model=list[UserOut])
def list_(_: User = Depends(require_role("admin")),
          db: Session = Depends(db_session)):
    return db.query(User).order_by(User.id.asc()).all()


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED)
def create(payload: UserCreate,
           _: User = Depends(require_role("admin")),
           db: Session = Depends(db_session)):
    try:
        u = user_service.create_user(db, payload.username, payload.password,
                                     payload.role, payload.display_name)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return u


def _get_or_404(db: Session, uid: int) -> User:
    u = db.get(User, uid)
    if not u:
        raise HTTPException(404, f"User {uid} not found")
    return u


@router.put("/{uid}", response_model=UserOut)
def update(uid: int, payload: UserUpdate,
           actor: User = Depends(require_role("admin")),
           db: Session = Depends(db_session)):
    u = _get_or_404(db, uid)
    try:
        user_service.update_user(
            db, u,
            role=payload.role,
            display_name=payload.display_name,
            is_active=payload.is_active,
            actor_user_id=actor.id,
        )
    except ValueError as e:
        raise HTTPException(400, str(e))
    return u


@router.post("/{uid}/reset-password", status_code=status.HTTP_204_NO_CONTENT)
def reset_password(uid: int, payload: ResetPasswordIn,
                   _: User = Depends(require_role("admin")),
                   db: Session = Depends(db_session)):
    u = _get_or_404(db, uid)
    user_service.reset_password(db, u, payload.new_password)
    return None


@router.delete("/{uid}", status_code=status.HTTP_204_NO_CONTENT)
def delete(uid: int,
           actor: User = Depends(require_role("admin")),
           db: Session = Depends(db_session)):
    u = _get_or_404(db, uid)
    try:
        user_service.deactivate_user(db, u, actor_user_id=actor.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return None
```

- [ ] **Step 2：在 `backend/app/main.py` 挂载 users router**

在 `from backend.app.routers import auth as auth_router` 下面加：

```python
from backend.app.routers import users as users_router
```

在 `app.include_router(auth_router.router)` 下面加：

```python
app.include_router(users_router.router)
```

- [ ] **Step 3：写 `backend/tests/test_users_api.py`**

```python
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
           json={"username": "root2", "password": "x", "role": "admin"})
    me = c.get("/api/v1/auth/me", headers=_h(t)).json()
    r = c.put(f"/api/v1/users/{me['id']}", headers=_h(t),
              json={"is_active": False})
    assert r.status_code == 400
    assert "自己" in r.json()["detail"]


def test_reset_password():
    c = TestClient(app)
    t = _admin_token(c)
    bob = c.post("/api/v1/users", headers=_h(t),
                 json={"username": "bob", "password": "pw", "role": "viewer"}).json()
    r = c.post(f"/api/v1/users/{bob['id']}/reset-password", headers=_h(t),
               json={"new_password": "newpw"})
    assert r.status_code == 204
    r = c.post("/api/v1/auth/login", json={"username": "bob", "password": "newpw"})
    assert r.status_code == 200


def test_delete_deactivates_and_kicks_session():
    c = TestClient(app)
    t = _admin_token(c)
    bob = c.post("/api/v1/users", headers=_h(t),
                 json={"username": "bob", "password": "pw", "role": "viewer"}).json()
    bt = c.post("/api/v1/auth/login",
                json={"username": "bob", "password": "pw"}).json()["session_token"]
    # bob 在线
    assert c.get("/api/v1/auth/me", headers=_h(bt)).status_code == 200
    # admin 删除 bob
    r = c.delete(f"/api/v1/users/{bob['id']}", headers=_h(t))
    assert r.status_code == 204
    # bob session 应失效
    assert c.get("/api/v1/auth/me", headers=_h(bt)).status_code == 401
```

- [ ] **Step 4：跑测试，确认通过**

```bash
cd backend && pytest tests/test_users_api.py -v
```

预期：8 个用例 PASS。

- [ ] **Step 5：commit**

```bash
git add backend/app/routers/users.py backend/app/main.py backend/tests/test_users_api.py
git commit -m "feat(backend): 加 /users router（admin 管理用户）"
```

---

## Task 12：现有 router 加 RBAC 依赖 + 跑全量测试

**Files:**
- Modify: `backend/app/routers/models.py`
- Modify: `backend/app/routers/judges.py`
- Modify: `backend/app/routers/tasks.py`
- Modify: `backend/app/routers/batches.py`
- Modify: `backend/app/routers/jobs.py`
- Modify: `backend/app/routers/predictions.py`
- Modify: `backend/app/routers/evaluations.py`
- Modify: `backend/tests/conftest.py`

策略：**所有 GET 端点** 加 `require_role("viewer", "operator", "admin")`；**所有 POST/PUT/DELETE 端点** 加 `require_role("operator", "admin")`。
为不破坏现有大量测试，conftest 中新增 fixture 注入"自动 Bearer 头"。

- [ ] **Step 1：修改 `backend/tests/conftest.py`**

替换为：

```python
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
```

- [ ] **Step 2：替换 `backend/app/routers/models.py` 中所有端点签名**

打开文件，给 `create / update / delete` 加 `_: User = Depends(require_role("operator", "admin"))`，给 `list_ / get` 加 `_: User = Depends(require_role("viewer", "operator", "admin"))`。

文件顶部 import 加：

```python
from backend.app.deps import require_role
from backend.app.models import User
```

各端点签名示例（保持其它参数不变，只多加 `_:` 参数）：

```python
@router.post("", ...)
def create(payload: ModelCreate,
           _: User = Depends(require_role("operator", "admin")),
           db: Session = Depends(db_session)):
    ...

@router.get("", ...)
def list_(_: User = Depends(require_role("viewer", "operator", "admin")),
          db: Session = Depends(db_session)):
    ...
```

> **重要：** `_:` 参数必须放在 `payload` 之后、`db` 之前；FastAPI 不依赖参数顺序，但保持一致便于阅读。

按上述规则，对以下 6 个 router 同样改造（GET → viewer+；POST/PUT/DELETE/cancel → operator+）：

- `backend/app/routers/judges.py`
- `backend/app/routers/tasks.py`（包括 `upload_dataset` POST 端点）
- `backend/app/routers/batches.py`（`create / rerun` 是写；`list_ / get / report / list_revisions` 是读）
- `backend/app/routers/jobs.py`（`cancel` 是写；其余是读）
- `backend/app/routers/predictions.py`（仅 GET）
- `backend/app/routers/evaluations.py`（仅 GET）

- [ ] **Step 3：跑全量后端测试**

```bash
cd backend && pytest tests/ -v
```

预期：所有原业务测试因 conftest 自动带 system token 仍通过；auth/users 测试不依赖该 fixture，使用 `raw_client` 路径不受影响。如有失败请回头补 `_:` 依赖。

- [ ] **Step 4：commit**

```bash
git add backend/app/routers/ backend/tests/conftest.py
git commit -m "feat(backend): 现有路由接入 RBAC，conftest 默认带 system token"
```

---

## Task 13：RBAC 端到端抽样测试

**Files:**
- Create: `backend/tests/test_rbac.py`

- [ ] **Step 1：写 `backend/tests/test_rbac.py`**

```python
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
```

- [ ] **Step 2：跑测试，确认通过**

```bash
cd backend && pytest tests/test_rbac.py -v
```

- [ ] **Step 3：commit**

```bash
git add backend/tests/test_rbac.py
git commit -m "test(backend): 加 RBAC 端到端抽样测试"
```

---

## Task 14：batch_service 接收 actor + 路由注入 + 扩展 BatchOut/JobOut

**Files:**
- Modify: `backend/app/services/batch_service.py`
- Modify: `backend/app/routers/batches.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/tests/test_batch_actor.py`

- [ ] **Step 1：修改 `backend/app/services/batch_service.py`**

把 `record_revision` 签名改为：

```python
def record_revision(
    db: Session, batch_id: int, change_type: str, change_summary: str,
    actor_user_id: int | None = None,
):
    rev = BatchRevision(
        batch_id=batch_id,
        rev_num=_next_rev_num(db, batch_id),
        change_type=change_type,
        change_summary=change_summary,
        snapshot_json=_snapshot(db, batch_id),
        actor_user_id=actor_user_id,
    )
    db.add(rev)
```

`create_batch` 改为：

```python
def create_batch(db: Session, payload, actor_user_id: int | None = None) -> Batch:
    # 校验 model/task 存在
    models = db.query(Model).filter(Model.id.in_(payload.model_ids)).all()
    if len(models) != len(payload.model_ids):
        raise ValueError("some model_id not found")
    tasks = db.query(Task).filter(Task.id.in_(payload.task_ids)).all()
    if len(tasks) != len(payload.task_ids):
        raise ValueError("some task_id not found")

    batch = Batch(
        name=payload.name,
        mode=payload.mode,
        default_eval_version=payload.default_eval_version,
        default_judge_id=payload.default_judge_id,
        notes=payload.notes,
        created_by_user_id=actor_user_id,
        last_modified_by_user_id=actor_user_id,
    )
    db.add(batch)
    db.flush()

    for m in models:
        for t in tasks:
            db.add(BatchCell(
                batch_id=batch.id, model_id=m.id, task_id=t.id,
            ))
    db.flush()

    for m in models:
        for t in tasks:
            infer_job = None
            if payload.mode in ("infer", "all"):
                infer_job = Job(
                    type="infer", batch_id=batch.id,
                    model_id=m.id, task_id=t.id,
                    params_json={},
                    created_by_user_id=actor_user_id,
                )
                db.add(infer_job)
                db.flush()
            if payload.mode in ("eval", "all"):
                eval_job = Job(
                    type="eval", batch_id=batch.id,
                    model_id=m.id, task_id=t.id,
                    params_json={"eval_version": batch.default_eval_version},
                    dependency_job_id=infer_job.id if infer_job else None,
                    created_by_user_id=actor_user_id,
                )
                db.add(eval_job)

    record_revision(db, batch.id, "create", f"create batch '{batch.name}'",
                    actor_user_id=actor_user_id)
    return batch
```

`rerun_batch` 改为同样接收并传递 `actor_user_id`：在函数签名加 `actor_user_id: int | None = None`，构造 `Job(...)` 时加 `created_by_user_id=actor_user_id`，更新 `batch.last_modified_by_user_id = actor_user_id`，调 `record_revision(...)` 传 `actor_user_id=actor_user_id`。完整代码：

```python
def rerun_batch(db: Session, batch_id: int, payload,
                actor_user_id: int | None = None) -> list[Job]:
    batch = db.get(Batch, batch_id)
    if not batch:
        raise ValueError("batch not found")
    batch.last_modified_by_user_id = actor_user_id

    jobs_created = []
    for mid in payload.model_ids:
        for tid in payload.task_ids:
            cell = db.get(BatchCell, (batch_id, mid, tid))
            if not cell:
                raise ValueError(f"cell not found for model={mid} task={tid}")

            if payload.dataset_version_id is not None:
                cell.dataset_version_id = payload.dataset_version_id

            infer_job = None
            if payload.what in ("infer", "both"):
                infer_job = Job(
                    type="infer", batch_id=batch_id,
                    model_id=mid, task_id=tid,
                    params_json={},
                    created_by_user_id=actor_user_id,
                )
                db.add(infer_job); db.flush()
                jobs_created.append(infer_job)

            if payload.what in ("eval", "both"):
                dep_id = infer_job.id if infer_job else None
                if payload.what == "eval" and cell.current_prediction_id:
                    dep_id = None
                eval_job = Job(
                    type="eval", batch_id=batch_id,
                    model_id=mid, task_id=tid,
                    params_json={"eval_version": batch.default_eval_version},
                    dependency_job_id=dep_id,
                    created_by_user_id=actor_user_id,
                )
                db.add(eval_job); db.flush()
                jobs_created.append(eval_job)

    record_revision(
        db, batch_id, "rerun",
        f"rerun {payload.what} for models={payload.model_ids} tasks={payload.task_ids}",
        actor_user_id=actor_user_id,
    )
    return jobs_created
```

- [ ] **Step 2：修改 `backend/app/routers/batches.py` 注入 current_user**

把 `from backend.app.deps import db_session` 行改为：

```python
from backend.app.deps import current_user, db_session, require_role
from backend.app.models import User as UserModel
```

`create` 端点改为：

```python
@router.post("", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def create(payload: BatchCreate,
           actor: UserModel = Depends(require_role("operator", "admin")),
           db: Session = Depends(db_session)):
    try:
        batch = create_batch(db, payload, actor_user_id=actor.id)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(batch)
    return batch
```

`rerun` 端点改为：

```python
@router.post("/{bid}/rerun", status_code=status.HTTP_201_CREATED)
def rerun(bid: int, payload: BatchRerun,
          actor: UserModel = Depends(require_role("operator", "admin")),
          db: Session = Depends(db_session)):
    batch = db.get(Batch, bid)
    if not batch:
        raise HTTPException(status_code=404, detail=f"Batch {bid} not found")
    try:
        jobs = rerun_batch(db, bid, payload, actor_user_id=actor.id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return {
        "batch_id": bid,
        "jobs_created": len(jobs),
        "job_ids": [j.id for j in jobs],
    }
```

- [ ] **Step 3：扩展 `backend/app/schemas.py` 中的 `BatchOut` 与 `JobOut`**

在 `BatchOut` 类中添加（保持其它字段不变）：

```python
    created_by: UserBrief | None = None
    last_modified_by: UserBrief | None = None
```

在 `JobOut` 类中添加：

```python
    created_by: UserBrief | None = None
```

> 由于 SQLAlchemy 已加 relationship（Task 3），FastAPI from_attributes 模式会自动取出。

- [ ] **Step 4：写 `backend/tests/test_batch_actor.py`**

```python
from fastapi.testclient import TestClient

from backend.app.db import get_session
from backend.app.main import app
from backend.app.services.user_service import create_user


def _seed_user(name="alice", role="operator"):
    with get_session() as s:
        from backend.app.models import User
        if not s.query(User).filter_by(username=name).first():
            create_user(s, name, "pw", role, None)
            s.commit()


def _seed_model_task():
    with get_session() as s:
        from backend.app.models import Model, Task
        m = Model(name="m1", host="h", port=1, model_name="m",
                  concurrency=1, gen_kwargs_json={}, model_config_key="local_qwen")
        t = Task(key="t1", type="custom", suite_name="s")
        s.add_all([m, t]); s.commit()
        return m.id, t.id


def test_create_batch_records_actor():
    _seed_user("alice", "operator")
    mid, tid = _seed_model_task()
    c = TestClient(app)
    token = c.post("/api/v1/auth/login",
                   json={"username": "alice", "password": "pw"}).json()["session_token"]
    r = c.post("/api/v1/batches",
               headers={"Authorization": f"Bearer {token}"},
               json={"name": "b1", "mode": "all",
                     "model_ids": [mid], "task_ids": [tid]})
    assert r.status_code == 201
    body = r.json()
    assert body["created_by"]["username"] == "alice"
    assert body["last_modified_by"]["username"] == "alice"

    # 关联 job 也带 created_by
    r = c.get("/api/v1/jobs",
              headers={"Authorization": f"Bearer {token}"},
              params={"batch_id": body["id"]})
    jobs = r.json()
    assert all(j["created_by"]["username"] == "alice" for j in jobs)
```

- [ ] **Step 5：跑测试**

```bash
cd backend && pytest tests/test_batch_actor.py tests/test_batch_create.py tests/test_batch_rerun.py -v
```

预期：新测试通过 + 原 batch 测试仍通过（旧测试通过 system token，actor=None，不影响业务逻辑）。

- [ ] **Step 6：commit**

```bash
git add backend/app/services/batch_service.py backend/app/routers/batches.py backend/app/schemas.py backend/tests/test_batch_actor.py
git commit -m "feat(backend): batch/job 写操作记录 actor，BatchOut/JobOut 扩展 created_by"
```

---

## Task 15：session 清理后台协程

**Files:**
- Create: `backend/app/services/session_cleanup.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1：实现 `backend/app/services/session_cleanup.py`**

```python
import asyncio
import logging

from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.services.auth_service import cleanup_expired_sessions


_log = logging.getLogger(__name__)


async def session_cleanup_loop():
    """后台协程：周期性清理过期 session。"""
    settings = get_settings()
    interval = settings.session_cleanup_interval_sec
    while True:
        try:
            with get_session() as s:
                n = cleanup_expired_sessions(s)
                s.commit()
                if n:
                    _log.info("cleaned %d expired session(s)", n)
        except Exception:
            _log.exception("session cleanup failed")
        await asyncio.sleep(interval)
```

- [ ] **Step 2：在 `backend/app/main.py` lifespan 中启动**

把 lifespan 函数改为：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task, _session_cleanup_task
    init_db()
    _worker_task = asyncio.create_task(worker_loop())
    from backend.app.services.session_cleanup import session_cleanup_loop
    _session_cleanup_task = asyncio.create_task(session_cleanup_loop())
    yield
    if _worker_task:
        _worker_task.cancel()
    if _session_cleanup_task:
        _session_cleanup_task.cancel()
```

- [ ] **Step 3：跑全量后端测试**

```bash
cd backend && pytest tests/ -v
```

预期：所有测试仍通过。

- [ ] **Step 4：commit**

```bash
git add backend/app/services/session_cleanup.py backend/app/main.py
git commit -m "feat(backend): 加 session 清理后台协程（每小时一次）"
```

---

## Task 16：前端 authStore + api.js 401 处理

**Files:**
- Modify: `frontend/src/store/authStore.js`
- Modify: `frontend/src/lib/api.js`

- [ ] **Step 1：替换 `frontend/src/store/authStore.js`**

```javascript
import { create } from 'zustand';

function loadUser() {
  try {
    return JSON.parse(localStorage.getItem('eval_auth_user') || 'null');
  } catch {
    return null;
  }
}

export const useAuthStore = create((set, get) => ({
  token: localStorage.getItem('eval_auth_token') || '',
  user: loadUser(),

  setSession: ({ session_token, user }) => {
    localStorage.setItem('eval_auth_token', session_token);
    localStorage.setItem('eval_auth_user', JSON.stringify(user));
    set({ token: session_token, user });
  },

  clearSession: () => {
    localStorage.removeItem('eval_auth_token');
    localStorage.removeItem('eval_auth_user');
    set({ token: '', user: null });
  },

  isAuthenticated: () => !!get().token && !!get().user,
  isAdmin: () => get().user?.role === 'admin',
  canWrite: () => ['admin', 'operator'].includes(get().user?.role),
}));
```

- [ ] **Step 2：在 `frontend/src/lib/api.js` 顶部导入 store 并改 `request()` 401 处理**

文件顶部加：

```javascript
import { useAuthStore } from '../store/authStore';
```

替换 `request` 函数：

```javascript
async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  const headers = { ...options.headers };

  const token = getToken();
  if (token) headers['Authorization'] = `Bearer ${token}`;

  if (!(options.body instanceof FormData)) {
    headers['Content-Type'] = 'application/json';
  }

  const res = await fetch(url, { ...options, headers });

  if (res.status === 401) {
    useAuthStore.getState().clearSession();
    if (window.location.pathname !== '/login') {
      window.location.href = '/login';
    }
    throw new Error('未登录或会话已过期');
  }

  if (!res.ok) {
    const err = await res.json().catch(() => ({}));
    throw new Error(err.detail || `HTTP ${res.status}`);
  }

  if (res.status === 204) return null;
  return res.json();
}
```

- [ ] **Step 3：在 `api` 对象中追加 `auth` 与 `users` 分组**

在 `export const api = {` 内追加（放在 `health` 后，其它分组前）：

```javascript
  auth: {
    login: (data) => request('/auth/login', { method: 'POST', body: JSON.stringify(data) }),
    logout: () => request('/auth/logout', { method: 'POST' }),
    me: () => request('/auth/me'),
    changePassword: (data) => request('/auth/change-password', { method: 'POST', body: JSON.stringify(data) }),
  },

  users: {
    list: () => request('/users'),
    create: (data) => request('/users', { method: 'POST', body: JSON.stringify(data) }),
    update: (id, data) => request(`/users/${id}`, { method: 'PUT', body: JSON.stringify(data) }),
    resetPassword: (id, data) => request(`/users/${id}/reset-password`, { method: 'POST', body: JSON.stringify(data) }),
    del: (id) => request(`/users/${id}`, { method: 'DELETE' }),
  },
```

- [ ] **Step 4：commit**

```bash
git add frontend/src/store/authStore.js frontend/src/lib/api.js
git commit -m "feat(frontend): authStore 加 user 字段；api.js 加 auth/users 分组与 401 自动登出"
```

---

## Task 17：用户显示工具

**Files:**
- Create: `frontend/src/lib/userDisplay.js`

- [ ] **Step 1：写 `frontend/src/lib/userDisplay.js`**

```javascript
/** 把后端返回的 created_by / last_modified_by 字段（UserBrief | null）格式化为显示字符串。 */
export function formatUser(user) {
  if (!user) return '系统';
  const name = user.display_name || user.username;
  if (user.is_active === false) return `${name}（已停用）`;
  return name;
}

/** 角色显示中文。 */
export function formatRole(role) {
  return { admin: '管理员', operator: '操作', viewer: '只读' }[role] || role;
}
```

- [ ] **Step 2：commit**

```bash
git add frontend/src/lib/userDisplay.js
git commit -m "feat(frontend): 加 formatUser / formatRole 显示工具"
```

---

## Task 18：路由守卫组件 + LoginPage

**Files:**
- Create: `frontend/src/components/auth/RequireAuth.jsx`
- Create: `frontend/src/components/auth/RequireAdmin.jsx`
- Create: `frontend/src/pages/LoginPage.jsx`
- Modify: `frontend/src/App.jsx`

- [ ] **Step 1：写 `frontend/src/components/auth/RequireAuth.jsx`**

```jsx
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

export function RequireAuth({ children }) {
  const isAuth = useAuthStore((s) => !!s.token && !!s.user);
  const loc = useLocation();
  if (!isAuth) {
    return <Navigate to="/login" replace state={{ from: loc.pathname }} />;
  }
  return children;
}
```

- [ ] **Step 2：写 `frontend/src/components/auth/RequireAdmin.jsx`**

```jsx
import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

export function RequireAdmin({ children }) {
  const role = useAuthStore((s) => s.user?.role);
  if (role !== 'admin') return <Navigate to="/" replace />;
  return children;
}
```

- [ ] **Step 3：写 `frontend/src/pages/LoginPage.jsx`**

```jsx
import { useState } from 'react';
import { useNavigate, useLocation } from 'react-router-dom';
import { api } from '../lib/api';
import { useAuthStore } from '../store/authStore';

export function LoginPage() {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const setSession = useAuthStore((s) => s.setSession);
  const nav = useNavigate();
  const loc = useLocation();
  const from = loc.state?.from || '/';

  async function onSubmit(e) {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const data = await api.auth.login({ username, password });
      setSession(data);
      nav(from, { replace: true });
    } catch (err) {
      setError(err.message || '登录失败');
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen flex items-center justify-center bg-gray-50">
      <form onSubmit={onSubmit}
            className="w-80 bg-white border border-gray-200 rounded-lg p-6 shadow-sm space-y-4">
        <h1 className="text-lg font-semibold text-gray-900 text-center">Eval Backend 登录</h1>

        <div>
          <label className="text-xs text-gray-600">用户名</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)}
                 autoFocus required
                 className="w-full mt-1 px-3 py-2 border border-gray-300 rounded text-sm" />
        </div>

        <div>
          <label className="text-xs text-gray-600">密码</label>
          <input type="password" value={password} onChange={(e) => setPassword(e.target.value)}
                 required
                 className="w-full mt-1 px-3 py-2 border border-gray-300 rounded text-sm" />
        </div>

        {error && <p className="text-xs text-red-600">{error}</p>}

        <button type="submit" disabled={loading}
                className="w-full py-2 rounded bg-primary-600 text-white text-sm font-medium hover:bg-primary-700 disabled:opacity-50">
          {loading ? '登录中…' : '登录'}
        </button>
      </form>
    </div>
  );
}
```

- [ ] **Step 4：改造 `frontend/src/App.jsx`**

替换为：

```jsx
import { createBrowserRouter, RouterProvider, Outlet } from 'react-router-dom';
import { Layout } from './components/layout/Layout';
import { RequireAuth } from './components/auth/RequireAuth';
import { RequireAdmin } from './components/auth/RequireAdmin';
import { DashboardPage } from './features/dashboard/DashboardPage';
import { ModelsPage } from './features/models/ModelsPage';
import { JudgesPage } from './features/judges/JudgesPage';
import { TasksPage } from './features/tasks/TasksPage';
import { BatchesPage } from './features/batches/BatchesPage';
import { BatchDetailPage } from './features/batches/BatchDetailPage';
import { JobsPage } from './features/jobs/JobsPage';
import { UsersPage } from './features/users/UsersPage';
import { SettingsPage } from './pages/SettingsPage';
import { LoginPage } from './pages/LoginPage';
import { NotFoundPage } from './pages/NotFoundPage';

const router = createBrowserRouter([
  { path: '/login', element: <LoginPage /> },
  {
    path: '/',
    element: (
      <RequireAuth>
        <Layout />
      </RequireAuth>
    ),
    children: [
      { index: true, element: <DashboardPage /> },
      { path: 'models', element: <ModelsPage /> },
      { path: 'judges', element: <JudgesPage /> },
      { path: 'tasks', element: <TasksPage /> },
      { path: 'batches', element: <BatchesPage /> },
      { path: 'batches/:id', element: <BatchDetailPage /> },
      { path: 'jobs', element: <JobsPage /> },
      { path: 'users', element: <RequireAdmin><UsersPage /></RequireAdmin> },
      { path: 'settings', element: <SettingsPage /> },
      { path: '*', element: <NotFoundPage /> },
    ],
  },
]);

export default function App() {
  return <RouterProvider router={router} />;
}
```

- [ ] **Step 5：commit**

> 注意：UsersPage 还未创建，本步会让前端构建报 import 错误。在 Task 19 中补齐。可先 commit 并继续。

```bash
git add frontend/src/components/auth/ frontend/src/pages/LoginPage.jsx frontend/src/App.jsx
git commit -m "feat(frontend): 加 RequireAuth/RequireAdmin 守卫与 LoginPage"
```

---

## Task 19：UsersPage + 弹窗

**Files:**
- Create: `frontend/src/features/users/UsersPage.jsx`
- Create: `frontend/src/features/users/components/UserFormModal.jsx`
- Create: `frontend/src/features/users/components/ResetPasswordModal.jsx`

- [ ] **Step 1：写 `frontend/src/features/users/components/UserFormModal.jsx`**

```jsx
import { useState, useEffect } from 'react';

export function UserFormModal({ open, onClose, onSubmit, initial }) {
  const isEdit = !!initial;
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [role, setRole] = useState('viewer');
  const [displayName, setDisplayName] = useState('');
  const [isActive, setIsActive] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    if (initial) {
      setUsername(initial.username);
      setRole(initial.role);
      setDisplayName(initial.display_name || '');
      setIsActive(initial.is_active);
    } else {
      setUsername(''); setPassword('');
      setRole('viewer'); setDisplayName(''); setIsActive(true);
    }
    setError('');
  }, [initial, open]);

  if (!open) return null;

  async function submit(e) {
    e.preventDefault();
    setError('');
    try {
      if (isEdit) {
        await onSubmit({ role, display_name: displayName, is_active: isActive });
      } else {
        await onSubmit({ username, password, role, display_name: displayName });
      }
      onClose();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <form onSubmit={submit}
            className="bg-white rounded-lg p-6 w-96 space-y-3">
        <h2 className="text-base font-semibold">{isEdit ? '编辑用户' : '新增用户'}</h2>

        <div>
          <label className="text-xs text-gray-600">用户名</label>
          <input value={username} onChange={(e) => setUsername(e.target.value)}
                 disabled={isEdit} required
                 className="w-full px-3 py-2 border rounded text-sm disabled:bg-gray-100" />
        </div>

        {!isEdit && (
          <div>
            <label className="text-xs text-gray-600">密码</label>
            <input type="password" value={password}
                   onChange={(e) => setPassword(e.target.value)} required
                   className="w-full px-3 py-2 border rounded text-sm" />
          </div>
        )}

        <div>
          <label className="text-xs text-gray-600">角色</label>
          <select value={role} onChange={(e) => setRole(e.target.value)}
                  className="w-full px-3 py-2 border rounded text-sm">
            <option value="viewer">viewer（只读）</option>
            <option value="operator">operator（操作）</option>
            <option value="admin">admin（管理员）</option>
          </select>
        </div>

        <div>
          <label className="text-xs text-gray-600">显示名（可选）</label>
          <input value={displayName} onChange={(e) => setDisplayName(e.target.value)}
                 className="w-full px-3 py-2 border rounded text-sm" />
        </div>

        {isEdit && (
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isActive}
                   onChange={(e) => setIsActive(e.target.checked)} />
            启用
          </label>
        )}

        {error && <p className="text-xs text-red-600">{error}</p>}

        <div className="flex gap-2 justify-end pt-2">
          <button type="button" onClick={onClose}
                  className="px-3 py-1.5 border rounded text-sm">取消</button>
          <button type="submit"
                  className="px-3 py-1.5 bg-primary-600 text-white rounded text-sm">
            保存
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 2：写 `frontend/src/features/users/components/ResetPasswordModal.jsx`**

```jsx
import { useState, useEffect } from 'react';

export function ResetPasswordModal({ open, onClose, onSubmit, username }) {
  const [pw, setPw] = useState('');
  const [error, setError] = useState('');

  useEffect(() => {
    if (open) { setPw(''); setError(''); }
  }, [open]);

  if (!open) return null;

  async function submit(e) {
    e.preventDefault();
    setError('');
    try {
      await onSubmit({ new_password: pw });
      onClose();
    } catch (err) {
      setError(err.message);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/40 flex items-center justify-center z-50">
      <form onSubmit={submit}
            className="bg-white rounded-lg p-6 w-80 space-y-3">
        <h2 className="text-base font-semibold">重置密码：{username}</h2>
        <input type="password" value={pw} onChange={(e) => setPw(e.target.value)}
               placeholder="新密码" required
               className="w-full px-3 py-2 border rounded text-sm" />
        {error && <p className="text-xs text-red-600">{error}</p>}
        <div className="flex gap-2 justify-end pt-2">
          <button type="button" onClick={onClose}
                  className="px-3 py-1.5 border rounded text-sm">取消</button>
          <button type="submit"
                  className="px-3 py-1.5 bg-primary-600 text-white rounded text-sm">
            确认重置
          </button>
        </div>
      </form>
    </div>
  );
}
```

- [ ] **Step 3：写 `frontend/src/features/users/UsersPage.jsx`**

```jsx
import { useEffect, useState } from 'react';
import { api } from '../../lib/api';
import { useAuthStore } from '../../store/authStore';
import { formatRole } from '../../lib/userDisplay';
import { UserFormModal } from './components/UserFormModal';
import { ResetPasswordModal } from './components/ResetPasswordModal';

export function UsersPage() {
  const me = useAuthStore((s) => s.user);
  const [users, setUsers] = useState([]);
  const [editing, setEditing] = useState(null);
  const [creating, setCreating] = useState(false);
  const [resetTarget, setResetTarget] = useState(null);
  const [error, setError] = useState('');

  async function load() {
    try {
      setUsers(await api.users.list());
    } catch (e) {
      setError(e.message);
    }
  }

  useEffect(() => { load(); }, []);

  async function handleCreate(data) {
    await api.users.create(data);
    await load();
  }

  async function handleUpdate(data) {
    await api.users.update(editing.id, data);
    setEditing(null);
    await load();
  }

  async function handleResetPassword(data) {
    await api.users.resetPassword(resetTarget.id, data);
  }

  async function handleDelete(u) {
    if (!confirm(`确认删除用户 ${u.username}？该操作会停用账号并踢下线。`)) return;
    try {
      await api.users.del(u.id);
      await load();
    } catch (e) {
      alert(e.message);
    }
  }

  return (
    <div className="p-6 space-y-4">
      <div className="flex justify-between items-center">
        <h1 className="text-xl font-semibold">用户管理</h1>
        <button onClick={() => setCreating(true)}
                className="px-3 py-1.5 bg-primary-600 text-white rounded text-sm">
          + 新增用户
        </button>
      </div>

      {error && <p className="text-sm text-red-600">{error}</p>}

      <table className="w-full text-sm border border-gray-200 bg-white">
        <thead className="bg-gray-50">
          <tr className="text-left text-xs text-gray-600">
            <th className="px-3 py-2">用户名</th>
            <th className="px-3 py-2">显示名</th>
            <th className="px-3 py-2">角色</th>
            <th className="px-3 py-2">状态</th>
            <th className="px-3 py-2">最后登录</th>
            <th className="px-3 py-2">创建时间</th>
            <th className="px-3 py-2">操作</th>
          </tr>
        </thead>
        <tbody>
          {users.map((u) => (
            <tr key={u.id} className="border-t">
              <td className="px-3 py-2">{u.username}</td>
              <td className="px-3 py-2">{u.display_name || '-'}</td>
              <td className="px-3 py-2">{formatRole(u.role)}</td>
              <td className="px-3 py-2">
                {u.is_active ? '启用' : <span className="text-gray-400">停用</span>}
              </td>
              <td className="px-3 py-2">{u.last_login_at?.slice(0, 19).replace('T', ' ') || '-'}</td>
              <td className="px-3 py-2">{u.created_at.slice(0, 19).replace('T', ' ')}</td>
              <td className="px-3 py-2 space-x-2">
                <button onClick={() => setEditing(u)}
                        className="text-primary-600 hover:underline">编辑</button>
                <button onClick={() => setResetTarget(u)}
                        className="text-primary-600 hover:underline">重置密码</button>
                <button onClick={() => handleDelete(u)}
                        disabled={u.id === me?.id}
                        title={u.id === me?.id ? '不能删除自己' : ''}
                        className="text-red-600 hover:underline disabled:text-gray-300 disabled:no-underline">
                  删除
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <UserFormModal
        open={creating}
        initial={null}
        onClose={() => setCreating(false)}
        onSubmit={handleCreate}
      />
      <UserFormModal
        open={!!editing}
        initial={editing}
        onClose={() => setEditing(null)}
        onSubmit={handleUpdate}
      />
      <ResetPasswordModal
        open={!!resetTarget}
        username={resetTarget?.username}
        onClose={() => setResetTarget(null)}
        onSubmit={handleResetPassword}
      />
    </div>
  );
}
```

- [ ] **Step 4：跑 `npm run build` 确认前端编译通过**

```bash
cd frontend && npm run build
```

预期：build 成功。

- [ ] **Step 5：commit**

```bash
git add frontend/src/features/users/
git commit -m "feat(frontend): 加 UsersPage 与新增/编辑/重置密码弹窗"
```

---

## Task 20：Sidebar 改造（用户卡片 + 用户管理入口 + 退出）

**Files:**
- Modify: `frontend/src/components/layout/Sidebar.jsx`

- [ ] **Step 1：替换 `frontend/src/components/layout/Sidebar.jsx` 为：**

```jsx
import { NavLink, useNavigate } from 'react-router-dom';
import {
  LayoutDashboard, Cpu, Gavel, ListChecks, FolderKanban,
  Activity, Settings, Users, LogOut,
} from 'lucide-react';
import { api } from '../../lib/api';
import { useAuthStore } from '../../store/authStore';
import { formatRole } from '../../lib/userDisplay';

const baseNav = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/models', icon: Cpu, label: '模型管理' },
  { to: '/judges', icon: Gavel, label: '打分模型' },
  { to: '/tasks', icon: ListChecks, label: '任务与数据' },
  { to: '/batches', icon: FolderKanban, label: '批次评测' },
  { to: '/jobs', icon: Activity, label: '执行记录' },
  { to: '/settings', icon: Settings, label: '设置' },
];

export function Sidebar() {
  const user = useAuthStore((s) => s.user);
  const isAdmin = useAuthStore((s) => s.isAdmin)();
  const clearSession = useAuthStore((s) => s.clearSession);
  const nav = useNavigate();

  const items = isAdmin
    ? [...baseNav.slice(0, -1),
       { to: '/users', icon: Users, label: '用户管理' },
       baseNav[baseNav.length - 1]]
    : baseNav;

  async function handleLogout() {
    try { await api.auth.logout(); } catch {}
    clearSession();
    nav('/login', { replace: true });
  }

  const displayName = user?.display_name || user?.username || '未登录';

  return (
    <aside className="w-56 bg-white border-r border-gray-200 flex flex-col h-screen sticky top-0">
      <div className="px-6 py-4 border-b border-gray-200">
        <h1 className="text-lg font-bold text-gray-900">Eval Backend</h1>
        <p className="text-xs text-gray-500 mt-0.5">评测管理系统</p>
      </div>

      {user && (
        <div className="px-4 py-3 border-b border-gray-200 text-sm">
          <div className="font-medium text-gray-900 truncate">{displayName}</div>
          <div className="text-xs text-gray-500 mt-0.5 flex items-center justify-between">
            <span>{formatRole(user.role)}</span>
            <button onClick={handleLogout}
                    className="text-gray-400 hover:text-red-600 inline-flex items-center gap-0.5">
              <LogOut size={12} /> 退出
            </button>
          </div>
        </div>
      )}

      <nav className="flex-1 px-3 py-4 space-y-1">
        {items.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.to === '/'}
            className={({ isActive }) =>
              `flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors ${
                isActive ? 'bg-primary-50 text-primary-700' : 'text-gray-700 hover:bg-gray-50'
              }`
            }
          >
            <item.icon size={18} />
            {item.label}
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-gray-200 text-xs text-gray-400">v0.2.0</div>
    </aside>
  );
}
```

- [ ] **Step 2：build 验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 3：commit**

```bash
git add frontend/src/components/layout/Sidebar.jsx
git commit -m "feat(frontend): Sidebar 加用户卡片/退出/用户管理入口"
```

---

## Task 21：SettingsPage 改造（删 token 卡片 + 加修改密码）

**Files:**
- Modify: `frontend/src/pages/SettingsPage.jsx`

- [ ] **Step 1：先看现有 SettingsPage 内容**

```bash
cat frontend/src/pages/SettingsPage.jsx
```

- [ ] **Step 2：替换 `frontend/src/pages/SettingsPage.jsx` 为：**

```jsx
import { useState } from 'react';
import { api } from '../lib/api';
import { useAuthStore } from '../store/authStore';
import { formatRole } from '../lib/userDisplay';

export function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const [oldPw, setOldPw] = useState('');
  const [newPw, setNewPw] = useState('');
  const [newPw2, setNewPw2] = useState('');
  const [msg, setMsg] = useState('');
  const [err, setErr] = useState('');
  const [loading, setLoading] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setMsg(''); setErr('');
    if (newPw !== newPw2) {
      setErr('两次输入的新密码不一致');
      return;
    }
    setLoading(true);
    try {
      await api.auth.changePassword({ old_password: oldPw, new_password: newPw });
      setMsg('修改成功');
      setOldPw(''); setNewPw(''); setNewPw2('');
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="p-6 max-w-xl space-y-6">
      <h1 className="text-xl font-semibold">设置</h1>

      <section className="bg-white border border-gray-200 rounded-lg p-5 space-y-3">
        <h2 className="text-base font-medium">当前账号</h2>
        <dl className="text-sm space-y-1">
          <div className="flex"><dt className="w-20 text-gray-500">用户名</dt><dd>{user?.username}</dd></div>
          <div className="flex"><dt className="w-20 text-gray-500">显示名</dt><dd>{user?.display_name || '-'}</dd></div>
          <div className="flex"><dt className="w-20 text-gray-500">角色</dt><dd>{formatRole(user?.role)}</dd></div>
        </dl>
      </section>

      <section className="bg-white border border-gray-200 rounded-lg p-5 space-y-3">
        <h2 className="text-base font-medium">修改密码</h2>
        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="text-xs text-gray-600">原密码</label>
            <input type="password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} required
                   className="w-full px-3 py-2 border rounded text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-600">新密码</label>
            <input type="password" value={newPw} onChange={(e) => setNewPw(e.target.value)} required
                   className="w-full px-3 py-2 border rounded text-sm" />
          </div>
          <div>
            <label className="text-xs text-gray-600">确认新密码</label>
            <input type="password" value={newPw2} onChange={(e) => setNewPw2(e.target.value)} required
                   className="w-full px-3 py-2 border rounded text-sm" />
          </div>
          {msg && <p className="text-xs text-green-600">{msg}</p>}
          {err && <p className="text-xs text-red-600">{err}</p>}
          <button type="submit" disabled={loading}
                  className="px-4 py-2 bg-primary-600 text-white text-sm rounded disabled:opacity-50">
            {loading ? '提交中…' : '保存'}
          </button>
        </form>
      </section>
    </div>
  );
}
```

- [ ] **Step 3：build 验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 4：commit**

```bash
git add frontend/src/pages/SettingsPage.jsx
git commit -m "feat(frontend): SettingsPage 显示当前账号 + 修改密码卡片"
```

---

## Task 22：BatchDetailPage 头部显示 创建人 / 最后修改人

**Files:**
- Modify: `frontend/src/features/batches/BatchDetailPage.jsx`

- [ ] **Step 1：查看当前 BatchDetailPage**

```bash
sed -n '1,60p' frontend/src/features/batches/BatchDetailPage.jsx
```

- [ ] **Step 2：在 BatchDetailPage 顶部 import 加：**

```javascript
import { formatUser } from '../../lib/userDisplay';
```

- [ ] **Step 3：在头部信息区追加两行**

定位到展示 batch 名称/状态的区块（通常在组件 JSX 顶部），追加：

```jsx
{batch && (
  <div className="text-xs text-gray-500 flex gap-4 mt-1">
    <span>创建人：{formatUser(batch.created_by)}</span>
    <span>最后修改人：{formatUser(batch.last_modified_by)}</span>
  </div>
)}
```

> 如果 `batch` 变量名为其它（如 `data`），请按现有变量名调整。

- [ ] **Step 4：build 验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 5：commit**

```bash
git add frontend/src/features/batches/BatchDetailPage.jsx
git commit -m "feat(frontend): BatchDetailPage 头部显示创建人/最后修改人"
```

---

## Task 23：JobsPage 列表新增"提交人"列

**Files:**
- Modify: `frontend/src/features/jobs/JobsPage.jsx`

- [ ] **Step 1：查看 JobsPage 现有表格结构**

```bash
sed -n '1,80p' frontend/src/features/jobs/JobsPage.jsx
```

- [ ] **Step 2：在文件顶部 import 加：**

```javascript
import { formatUser } from '../../lib/userDisplay';
```

- [ ] **Step 3：在表格 `<thead>` 中插入"提交人"列头**

在合适位置（一般在 `状态` 之后、`时间` 之前）插入：

```jsx
<th className="px-3 py-2">提交人</th>
```

在 `<tbody>` 的 `tr` 中对应位置插入：

```jsx
<td className="px-3 py-2">{formatUser(job.created_by)}</td>
```

> 变量名按文件实际情况调整（可能是 `j` 或 `row`）。

- [ ] **Step 4：build 验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 5：commit**

```bash
git add frontend/src/features/jobs/JobsPage.jsx
git commit -m "feat(frontend): JobsPage 列表加提交人列"
```

---

## Task 24：RoleButton + 给写按钮加门禁（轻量）

**Files:**
- Create: `frontend/src/components/ui/RoleButton.jsx`
- Modify: `frontend/src/features/models/ModelsPage.jsx`
- Modify: `frontend/src/features/judges/JudgesPage.jsx`
- Modify: `frontend/src/features/tasks/TasksPage.jsx`
- Modify: `frontend/src/features/batches/BatchesPage.jsx`
- Modify: `frontend/src/features/batches/BatchDetailPage.jsx`
- Modify: `frontend/src/features/jobs/JobsPage.jsx`

- [ ] **Step 1：写 `frontend/src/components/ui/RoleButton.jsx`**

```jsx
import { useAuthStore } from '../../store/authStore';

/**
 * 写操作按钮包装：viewer 角色置灰 + tooltip。
 * 使用：<RoleButton onClick={...} className="...">新建</RoleButton>
 */
export function RoleButton({ children, disabled, ...props }) {
  const canWrite = useAuthStore((s) => s.canWrite)();
  const blocked = !canWrite;
  return (
    <button
      {...props}
      disabled={disabled || blocked}
      title={blocked ? '当前角色无写权限' : props.title}
      className={(props.className || '') + (blocked ? ' opacity-50 cursor-not-allowed' : '')}
    >
      {children}
    </button>
  );
}
```

- [ ] **Step 2：替换写操作按钮**

在每个改动的 page 文件中，把"新建/创建/删除/编辑/rerun/取消"等触发写操作的 `<button>` 替换为 `<RoleButton>`。

示例（对 ModelsPage）：

```jsx
import { RoleButton } from '../../components/ui/RoleButton';

// ...原来的：
// <button onClick={openCreate} className="...">+ 新增模型</button>

// 改为：
<RoleButton onClick={openCreate} className="px-3 py-1.5 bg-primary-600 text-white rounded text-sm">
  + 新增模型
</RoleButton>
```

> **范围**：仅替换"新建/编辑/删除/rerun/取消"这类触发写 API 的按钮，普通"刷新""筛选"等读操作按钮保持原样。

- [ ] **Step 3：build 验证**

```bash
cd frontend && npm run build
```

- [ ] **Step 4：commit**

```bash
git add frontend/src/components/ui/RoleButton.jsx \
        frontend/src/features/models/ModelsPage.jsx \
        frontend/src/features/judges/JudgesPage.jsx \
        frontend/src/features/tasks/TasksPage.jsx \
        frontend/src/features/batches/BatchesPage.jsx \
        frontend/src/features/batches/BatchDetailPage.jsx \
        frontend/src/features/jobs/JobsPage.jsx
git commit -m "feat(frontend): 写操作按钮接入 RoleButton 角色门禁"
```

---

## Task 25：补 .env.example、文档与端到端联调

**Files:**
- Create / Modify: `backend/.env.example`（如果不存在则创建）
- Modify: `my_doc/deploy.md`

- [ ] **Step 1：写 / 更新 `backend/.env.example`**

```bash
# 评测后端基础配置
EVAL_BACKEND_BACKEND_DATA_DIR=./backend_data
EVAL_BACKEND_WORKSPACE_DIR=/opt/eval_workspace
EVAL_BACKEND_CODE_DIR=/opt/eval_workspace/code
EVAL_BACKEND_DOCKER_IMAGE_TAG=benchmark-eval:latest

# 旧 bypass token（可选；CI/调试用，生产请置空或注释）
# EVAL_BACKEND_AUTH_TOKEN=optional-system-token

# 权限系统：超级管理员（仅首次启动初始化使用，已有 admin 用户则忽略）
EVAL_BACKEND_ADMIN_USERNAME=admin
EVAL_BACKEND_ADMIN_PASSWORD=请改为强密码

# 会话 TTL（小时），默认 7 天
EVAL_BACKEND_SESSION_TTL_HOURS=168

# 过期 session 清理周期（秒），默认每小时一次
EVAL_BACKEND_SESSION_CLEANUP_INTERVAL_SEC=3600
```

- [ ] **Step 2：在 `my_doc/deploy.md` 末尾追加权限系统部署小节**

```markdown
---

## 8. 权限管理（v0.2 起）

### 8.1 首次启动初始化超级管理员

在 `.env` 中配置：

```bash
EVAL_BACKEND_ADMIN_USERNAME=admin
EVAL_BACKEND_ADMIN_PASSWORD=请改为强密码
```

启动后端后，若数据库中还没有该 username 的用户，将自动创建一个 admin。
**已存在则不会被覆盖**（DB 为准），后续如需轮换密码请在前端 SettingsPage 修改。

### 8.2 角色

- `admin`：管理员（含 operator 全部能力 + 用户管理）
- `operator`：操作（可新建/编辑/删除/rerun 等）
- `viewer`：只读（仅可查看）

### 8.3 旧的 EVAL_BACKEND_AUTH_TOKEN

仍然保留作为虚拟系统 admin bypass。生产部署建议**留空**（不配置该变量），仅 CI/本地调试时使用。
```

- [ ] **Step 3：跑全量后端测试**

```bash
cd backend && pytest tests/ -v
```

预期：全部通过。

- [ ] **Step 4：跑前端 build**

```bash
cd frontend && npm run build
```

- [ ] **Step 5：手动端到端联调（启本地 dev）**

启动后端：

```bash
cd backend && EVAL_BACKEND_ADMIN_PASSWORD=test123 uvicorn backend.app.main:app --reload --port 8080
```

启动前端 dev：

```bash
cd frontend && npm run dev
```

浏览器访问 `http://localhost:5173`：

1. 跳转到 `/login`，输入 `admin / test123`，应成功登录到 Dashboard
2. Sidebar 顶部显示 "超级管理员 · 管理员 · 退出"
3. 看到 "用户管理" 菜单
4. 进入"用户管理" → 新增 `bob / pw / viewer`
5. 退出，用 bob 登录 → Sidebar 不显示"用户管理"菜单
6. 进入 "模型管理"，"+ 新增模型" 按钮置灰 + tooltip "当前角色无写权限"
7. 退出，用 admin 重新登录 → 一切正常

- [ ] **Step 6：commit**

```bash
git add backend/.env.example my_doc/deploy.md
git commit -m "docs: 补 .env.example 与权限系统部署说明"
```

---

## 完成与回归

- [ ] **Final Step：跑所有后端测试**

```bash
cd backend && pytest tests/ -v
```

预期：全部 PASS。

- [ ] **Final Step：跑前端 build**

```bash
cd frontend && npm run build
```

预期：成功。

- [ ] **Final Step：检查 git 状态干净**

```bash
git status
```

预期：working tree clean。

---

## 注意事项

1. 实施过程中如发现某些 router 文件结构与预期不符，按"GET → viewer+；其余写 → operator+"原则灵活调整。
2. 前端 `BatchDetailPage` / `JobsPage` 的具体表格结构可能有差异，按现有变量名与位置局部插入即可。
3. 旧 `EVAL_BACKEND_AUTH_TOKEN` bypass 是兼容性设计，请勿删除（CI 测试 conftest 也依赖它）。
4. 如执行中遇到 SQLite 表已存在但缺列的旧库，迁移脚本会自动补列；新库则直接由 `create_all` 一步到位。
