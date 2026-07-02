# 评测后端系统 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建一个轻量 FastAPI 后端，把当前基于 bash + docker 的手动评测流程，包装成可编排、可增量更新、可追溯的服务；支持"多模型 × 多任务"的批次评测、局部重跑、老数据集版本化更新、批次历史回放。

**Architecture:** 单进程 FastAPI（HTTP 路由 + asyncio Worker 协程），SQLite 存元数据，文件系统存推理/评测产物。后端 Worker 轮询 Job 表，subprocess 调 `docker run` 复用现有 `eval_entry.py` / `eval_judge.py`，不改动 ais_bench 框架。Batch 作为"可变视图"，BatchCell 存当前指针，每次变更强制 append BatchRevision 历史，实现"A + 强制历史记录"语义。

**Tech Stack:** Python 3.10+, FastAPI, SQLAlchemy 2.x, SQLite, Pydantic v2, asyncio, docker CLI (via subprocess), pytest + httpx

---

## 与现有流程的关系

| 现状 | 后端系统替换/复用 |
|------|-------------------|
| `scripts/handle_run/multi_deploy_benchmark_v3.sh`（批量调度器） | **替换**：由 `POST /batches` 承担编排职责 |
| `run_mixed_benchmark.sh`（单任务执行器） | **替换**：由 Worker 拼装等价的 `docker run` 命令 |
| `.env` 文件（每工作区一份） | **替换**：Worker 为每个 job 动态生成临时 env 文件 |
| `eval_entry.py` / `eval_judge.py` | **复用**：作为容器内实际执行主体，不改 |
| `ais_bench/` 框架 | **复用**：完全不碰 |
| `outputs/{task_id}/` 目录结构 | **复用**：作为 Prediction/Evaluation 产物位置，后端只在 DB 里登记路径 |

---

## 关键设计

### 1. 数据模型（SQLite，10 张表）

```
Model             (id, name, host, port, model_name, concurrency, gen_kwargs_json,
                   model_config_key, created_at, updated_at)
  -- model_config_key 对应 ais_bench/benchmark/configs/models/ 下的文件名，如 'local_qwen'

JudgeLLM          (id, name, host, port, model_name, auth_ref, extra_env_json,
                   created_at, updated_at)

Task              (id, key, type[custom|generic], suite_name, display_name,
                   custom_task_num [nullable], default_data_rel_path [nullable],
                   is_llm_judge [bool], created_at)
  -- key 就是任务唯一键（task_34_suite / mmlu_redux_gen_5_shot_str）
  -- custom_task_num 对应 eval_entry.py --tasks 参数（34/36/...），仅 custom 类型有值

DatasetVersion    (id, task_id, tag, data_path, content_hash, is_default,
                   uploaded_at, note)
  -- data_path：相对 data/ 目录的路径；is_default 标记 Task 当前默认版本

Prediction        (id, model_id, task_id, dataset_version_id,
                   status[pending|running|success|failed],
                   output_task_id [ais_bench 的 task_id，对应 outputs/{task_id}],
                   output_path [绝对路径], num_samples, duration_sec,
                   job_id, created_at, finished_at, error_msg)
  -- 不可变（生成后不改）

Evaluation        (id, prediction_id, eval_version, judge_id [nullable],
                   status, accuracy, details_path, num_samples, duration_sec,
                   job_id, created_at, finished_at, error_msg)
  -- 不可变

Batch             (id, name, mode[infer|eval|all], default_eval_version,
                   default_judge_id [nullable], notes, created_at, updated_at)

BatchCell         (batch_id, model_id, task_id, dataset_version_id,
                   current_prediction_id [nullable], current_evaluation_id [nullable],
                   updated_at,
                   PRIMARY KEY (batch_id, model_id, task_id))
  -- 可变指针

BatchRevision     (id, batch_id, rev_num, change_type, change_summary,
                   snapshot_json, created_at)
  -- 每次 cell 变更 append 一条，snapshot_json 存当时所有 cell 的引用快照

Job               (id, type[infer|eval], params_json, status,
                   log_path, pid, returncode,
                   batch_id [nullable], model_id, task_id,
                   produces_prediction_id [nullable],
                   produces_evaluation_id [nullable],
                   dependency_job_id [nullable],
                   created_at, started_at, finished_at, error_msg)
```

**不变式**：
- `Prediction` / `Evaluation` 一经 `status=success` 不再修改
- `BatchCell` 每次指针变化必须写一条 `BatchRevision`（在同一事务内）
- 同一 `(batch_id, model_id, task_id)` 只能有一条 cell

### 2. API 面

```
# 配置 CRUD
POST   /api/v1/models                     注册推理服务
GET    /api/v1/models
GET    /api/v1/models/{id}
PUT    /api/v1/models/{id}
DELETE /api/v1/models/{id}

POST   /api/v1/judges                     注册打分 LLM
GET    /api/v1/judges
GET    /api/v1/judges/{id}
PUT    /api/v1/judges/{id}
DELETE /api/v1/judges/{id}

# 任务与数据集
GET    /api/v1/tasks                      预定义任务列表
GET    /api/v1/tasks/{id}
POST   /api/v1/tasks/{id}/datasets        上传老任务的新数据版本（multipart）
GET    /api/v1/tasks/{id}/datasets        列出该任务所有数据版本

# 批次
POST   /api/v1/batches                    创建批次（触发 jobs）
GET    /api/v1/batches
GET    /api/v1/batches/{id}
GET    /api/v1/batches/{id}/report        战报（基于当前指针组合）
GET    /api/v1/batches/{id}/report?rev=N  指定历史 revision 的战报
POST   /api/v1/batches/{id}/rerun         局部重跑
GET    /api/v1/batches/{id}/revisions

# 执行
GET    /api/v1/jobs
GET    /api/v1/jobs/{id}
GET    /api/v1/jobs/{id}/log
POST   /api/v1/jobs/{id}/cancel
GET    /api/v1/predictions/{id}
GET    /api/v1/evaluations/{id}

# 系统
GET    /api/v1/health
```

### 3. 执行机制

```
┌─── FastAPI 单进程 ──────────────────────┐
│  HTTP routes (FastAPI)                  │
│                                         │
│  Worker 协程 (asyncio.create_task)      │
│    ├ 每秒 poll Job 表 where status=pending
│    ├ 检查 Model.concurrency 全局配额    │
│    ├ 拼 docker run 命令（env 临时文件） │
│    ├ subprocess.Popen, 存 pid          │
│    ├ 异步 wait → 更新 status/returncode │
│    └ 执行 on_finish hook：              │
│        infer → 登记 Prediction + 切 cell│
│        eval  → 登记 Evaluation + 切 cell│
│                每次切 cell 新增 Revision│
└──────────────────────┬──────────────────┘
                       │
          subprocess.Popen("docker run ...")
                       │
┌──────────────────────┴──────────────────┐
│ docker container (benchmark-eval:latest)│
│  eval_entry.py / eval_judge.py          │
│  └ ais_bench --mode infer|eval ...      │
└─────────────────────────────────────────┘
                       │
         outputs/{output_task_id}/
              └ predictions/, eval_*/, ...
```

**Docker 命令拼装原则**（与 `run_mixed_benchmark.sh` 等价）：

推理 Job：
```
docker run --rm \
    --memory=128g --memory-swap=128g --shm-size=16g \
    --env-file /tmp/eval_backend/envs/{job_id}.env \
    -v {workspace}/data:/app/data \
    -v {workspace}/outputs:/app/outputs \
    -v {code_dir}/eval_entry.py:/app/eval_entry.py \
    -v {code_dir}/eval_judge.py:/app/eval_judge.py \
    -v {code_dir}/scripts:/app/scripts \
    --name eval-{job_id}-infer \
    benchmark-eval:latest \
    python eval_entry.py \
        --task-id {output_task_id} \
        --model-config {model.model_config_key} \
        --tasks {custom_num}               # 如果是 custom
        --generic-datasets {suite_name}    # 如果是 generic
```

评测 Job：
```
... 同上挂载 ...
python eval_judge.py \
    --infer-task {output_task_id} \
    --eval-version {eval_version} \
    --eval-tasks {suite_name}
```

每次一个 `(model, task)` 对起一个独立 docker 容器。并发由 Worker 控制，不再依赖 docker 自身。

### 4. 文件系统布局

```
{workspace}/                                ← 即现有 /opt/eval_workspace
├── .env.template                           模板（后端不再读）
├── data/
│   ├── custom_task/                        默认老数据
│   ├── <generic_suites>/
│   └── versions/                           ← 后端新增：数据集版本化存储
│       └── {task_key}/
│           └── {version_tag}/
│               └── data.jsonl
├── outputs/
│   └── {output_task_id}/                   ← Prediction/Evaluation 产物
│       ├── details/
│       └── eval_{version}/
├── backend/                                ← 本次新增
│   ├── app/
│   ├── tests/
│   └── pyproject.toml
└── backend_data/                           ← 本次新增
    ├── eval_backend.db                     SQLite
    ├── envs/                               每 job 临时 env 文件
    └── logs/
        └── job_{id}.log
```

---

## 文件结构（新增 / 修改）

| 操作 | 文件路径 | 职责 |
|------|---------|------|
| **新增** | `backend/pyproject.toml` | 后端独立依赖 |
| **新增** | `backend/app/__init__.py` | 包初始化 |
| **新增** | `backend/app/main.py` | FastAPI 入口 |
| **新增** | `backend/app/config.py` | 配置加载（yaml/env） |
| **新增** | `backend/app/db.py` | SQLAlchemy engine/session |
| **新增** | `backend/app/models.py` | 10 张表的 ORM 定义 |
| **新增** | `backend/app/schemas.py` | Pydantic 请求/响应模型 |
| **新增** | `backend/app/deps.py` | FastAPI 依赖注入（DB session、token） |
| **新增** | `backend/app/routers/models.py` | /models CRUD |
| **新增** | `backend/app/routers/judges.py` | /judges CRUD |
| **新增** | `backend/app/routers/tasks.py` | /tasks 只读 + 数据集版本 |
| **新增** | `backend/app/routers/batches.py` | /batches 创建/查询/rerun/report |
| **新增** | `backend/app/routers/jobs.py` | /jobs 查询 |
| **新增** | `backend/app/services/docker_runner.py` | docker run 命令拼装与执行 |
| **新增** | `backend/app/services/worker.py` | Worker 主循环 + on_finish hooks |
| **新增** | `backend/app/services/batch_service.py` | Batch 创建/rerun 业务逻辑 |
| **新增** | `backend/app/services/scan.py` | 扫描 outputs/ 解析 Prediction/Evaluation |
| **新增** | `backend/app/services/seed.py` | 从 ais_bench configs 初始化 Task 表 |
| **新增** | `backend/app/auth.py` | 可选全局 token 中间件 |
| **新增** | `backend/tests/conftest.py` | pytest fixture（临时 DB、mock docker） |
| **新增** | `backend/tests/test_*.py` | 每模块一份测试 |
| **新增** | `backend/scripts/seed_tasks.py` | 初始化任务表的 CLI |
| **新增** | `backend/README.md` | 后端部署/运行说明 |
| **不动** | `eval_entry.py`, `eval_judge.py`, `ais_bench/` | 完全不改 |

---

## 分阶段实施

**阶段策略**：
- **P0** 先跑通最小闭环：创建批次 → 执行 → 看战报。细化到 Step 级。
- **P1** 在 P0 完成后再细化 Step，本计划只描述 Task 目标与关键实现点。
- **P2** 保留标题，完全不阻塞 P0/P1。

---

## P0：最小可用闭环

### P0-Task 1: 后端项目骨架

**Files:**
- Create: `backend/pyproject.toml`
- Create: `backend/app/__init__.py`
- Create: `backend/app/main.py`
- Create: `backend/app/config.py`
- Create: `backend/tests/__init__.py`
- Create: `backend/tests/test_health.py`
- Create: `backend/README.md`

- [ ] **Step 1: 写失败测试 - /health 返回 200**

创建 `backend/tests/test_health.py`:
```python
from fastapi.testclient import TestClient
from backend.app.main import app


def test_health():
    client = TestClient(app)
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_health.py -v`
Expected: FAIL（ModuleNotFoundError: backend.app.main）

- [ ] **Step 3: 写 pyproject.toml**

创建 `backend/pyproject.toml`:
```toml
[project]
name = "eval-backend"
version = "0.1.0"
requires-python = ">=3.10"
dependencies = [
    "fastapi>=0.115",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "pydantic>=2.8",
    "pydantic-settings>=2.4",
    "pyyaml>=6.0",
    "python-multipart>=0.0.9",
]

[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27", "pytest-asyncio>=0.23"]

[tool.pytest.ini_options]
pythonpath = ["."]
asyncio_mode = "auto"
```

- [ ] **Step 4: 写 config 模块**

创建 `backend/app/config.py`:
```python
from pathlib import Path
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    backend_data_dir: Path = Path("./backend_data")
    workspace_dir: Path = Path("/opt/eval_workspace")
    code_dir: Path = Path("/opt/eval_workspace/code")
    docker_image_tag: str = "benchmark-eval:latest"
    worker_poll_interval_sec: float = 1.0
    default_job_concurrency: int = 4
    auth_token: str | None = None

    @property
    def db_path(self) -> Path:
        return self.backend_data_dir / "eval_backend.db"

    @property
    def envs_dir(self) -> Path:
        return self.backend_data_dir / "envs"

    @property
    def logs_dir(self) -> Path:
        return self.backend_data_dir / "logs"

    class Config:
        env_prefix = "EVAL_BACKEND_"
        env_file = ".env"


def get_settings() -> Settings:
    return Settings()
```

- [ ] **Step 5: 写 main.py**

创建 `backend/app/__init__.py`（空文件）。
创建 `backend/app/main.py`:
```python
from fastapi import FastAPI

app = FastAPI(title="Eval Backend", version="0.1.0")


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: 验证测试通过**

Run: `cd backend && pip install -e '.[dev]' && pytest tests/test_health.py -v`
Expected: PASS

- [ ] **Step 7: 写 README**

创建 `backend/README.md`:
```markdown
# 评测后端

## 运行

    cd backend
    pip install -e '.[dev]'
    uvicorn app.main:app --reload --port 8080

## 测试

    pytest -v
```

- [ ] **Step 8: 提交**

```bash
git add backend/
git commit -m "feat(backend): 后端骨架 + /health endpoint"
```

---

### P0-Task 2: 数据库 Schema

**Files:**
- Create: `backend/app/db.py`
- Create: `backend/app/models.py`
- Create: `backend/tests/test_models.py`

- [ ] **Step 1: 写失败测试 - 能建表并插入 Model 记录**

创建 `backend/tests/test_models.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import Base, Model


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'test.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_create_model(session):
    m = Model(name="qwen32b", host="10.0.0.1", port=9092,
              model_name="qwen3-32b", concurrency=20,
              model_config_key="local_qwen")
    session.add(m)
    session.commit()
    assert m.id is not None


def test_all_tables_created(session):
    from backend.app.models import (
        Model, JudgeLLM, Task, DatasetVersion, Prediction,
        Evaluation, Batch, BatchCell, BatchRevision, Job,
    )
    engine = session.get_bind()
    tables = set(Base.metadata.tables.keys())
    expected = {"models", "judges", "tasks", "dataset_versions",
                "predictions", "evaluations", "batches",
                "batch_cells", "batch_revisions", "jobs"}
    assert expected <= tables
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: FAIL（模块不存在）

- [ ] **Step 3: 写 models.py（10 张表）**

创建 `backend/app/models.py`:
```python
from datetime import datetime
from sqlalchemy import (
    Column, Integer, String, Float, Boolean, ForeignKey,
    DateTime, Text, JSON, UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


def _now():
    return datetime.utcnow()


class Model(Base):
    __tablename__ = "models"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    model_name = Column(String, nullable=False)
    concurrency = Column(Integer, default=20)
    gen_kwargs_json = Column(JSON, default=dict)
    model_config_key = Column(String, default="local_qwen")
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class JudgeLLM(Base):
    __tablename__ = "judges"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    host = Column(String, nullable=False)
    port = Column(Integer, nullable=False)
    model_name = Column(String, nullable=False)
    auth_ref = Column(String)
    extra_env_json = Column(JSON, default=dict)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class Task(Base):
    __tablename__ = "tasks"
    id = Column(Integer, primary_key=True)
    key = Column(String, unique=True, nullable=False)
    type = Column(String, nullable=False)  # custom | generic
    suite_name = Column(String, nullable=False)
    display_name = Column(String)
    custom_task_num = Column(Integer)
    default_data_rel_path = Column(String)
    is_llm_judge = Column(Boolean, default=False)
    created_at = Column(DateTime, default=_now)


class DatasetVersion(Base):
    __tablename__ = "dataset_versions"
    id = Column(Integer, primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    tag = Column(String, nullable=False)
    data_path = Column(String, nullable=False)
    content_hash = Column(String)
    is_default = Column(Boolean, default=False)
    uploaded_at = Column(DateTime, default=_now)
    note = Column(Text)
    __table_args__ = (UniqueConstraint("task_id", "tag"),)


class Prediction(Base):
    __tablename__ = "predictions"
    id = Column(Integer, primary_key=True)
    model_id = Column(Integer, ForeignKey("models.id"), nullable=False)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"))
    status = Column(String, default="pending")
    output_task_id = Column(String)  # ais_bench 的 task_id
    output_path = Column(String)
    num_samples = Column(Integer)
    duration_sec = Column(Float)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    created_at = Column(DateTime, default=_now)
    finished_at = Column(DateTime)
    error_msg = Column(Text)


class Evaluation(Base):
    __tablename__ = "evaluations"
    id = Column(Integer, primary_key=True)
    prediction_id = Column(Integer, ForeignKey("predictions.id"), nullable=False)
    eval_version = Column(String, nullable=False)
    judge_id = Column(Integer, ForeignKey("judges.id"))
    status = Column(String, default="pending")
    accuracy = Column(Float)
    details_path = Column(String)
    num_samples = Column(Integer)
    duration_sec = Column(Float)
    job_id = Column(Integer, ForeignKey("jobs.id"))
    created_at = Column(DateTime, default=_now)
    finished_at = Column(DateTime)
    error_msg = Column(Text)


class Batch(Base):
    __tablename__ = "batches"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    mode = Column(String, default="all")  # infer | eval | all
    default_eval_version = Column(String, default="eval_init")
    default_judge_id = Column(Integer, ForeignKey("judges.id"))
    notes = Column(Text)
    created_at = Column(DateTime, default=_now)
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class BatchCell(Base):
    __tablename__ = "batch_cells"
    batch_id = Column(Integer, ForeignKey("batches.id"), primary_key=True)
    model_id = Column(Integer, ForeignKey("models.id"), primary_key=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), primary_key=True)
    dataset_version_id = Column(Integer, ForeignKey("dataset_versions.id"))
    current_prediction_id = Column(Integer, ForeignKey("predictions.id"))
    current_evaluation_id = Column(Integer, ForeignKey("evaluations.id"))
    updated_at = Column(DateTime, default=_now, onupdate=_now)


class BatchRevision(Base):
    __tablename__ = "batch_revisions"
    id = Column(Integer, primary_key=True)
    batch_id = Column(Integer, ForeignKey("batches.id"), nullable=False)
    rev_num = Column(Integer, nullable=False)
    change_type = Column(String, nullable=False)
    change_summary = Column(Text)
    snapshot_json = Column(JSON)
    created_at = Column(DateTime, default=_now)
    __table_args__ = (UniqueConstraint("batch_id", "rev_num"),)


class Job(Base):
    __tablename__ = "jobs"
    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)  # infer | eval
    params_json = Column(JSON, default=dict)
    status = Column(String, default="pending")
    log_path = Column(String)
    pid = Column(Integer)
    returncode = Column(Integer)
    batch_id = Column(Integer, ForeignKey("batches.id"))
    model_id = Column(Integer, ForeignKey("models.id"))
    task_id = Column(Integer, ForeignKey("tasks.id"))
    produces_prediction_id = Column(Integer, ForeignKey("predictions.id"))
    produces_evaluation_id = Column(Integer, ForeignKey("evaluations.id"))
    dependency_job_id = Column(Integer, ForeignKey("jobs.id"))
    created_at = Column(DateTime, default=_now)
    started_at = Column(DateTime)
    finished_at = Column(DateTime)
    error_msg = Column(Text)
```

- [ ] **Step 4: 写 db.py**

创建 `backend/app/db.py`:
```python
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


def get_session() -> Session:
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()
```

- [ ] **Step 5: main.py 启动时 init_db**

Modify `backend/app/main.py`:
```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

from backend.app.db import init_db


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Eval Backend", version="0.1.0", lifespan=lifespan)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: 验证测试通过**

Run: `cd backend && pytest tests/test_models.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/app/db.py backend/app/models.py backend/app/main.py backend/tests/test_models.py
git commit -m "feat(backend): 10张表 ORM + SQLite 初始化"
```

---

### P0-Task 3: Task 种子初始化

**Files:**
- Create: `backend/app/services/__init__.py`
- Create: `backend/app/services/seed.py`
- Create: `backend/scripts/seed_tasks.py`
- Create: `backend/tests/test_seed.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_seed.py`:
```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from backend.app.models import Base, Task
from backend.app.services.seed import seed_generic_tasks, seed_custom_tasks


@pytest.fixture
def session(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path/'t.db'}")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        yield s


def test_seed_generic_tasks_inserts_known_suites(session):
    seed_generic_tasks(session, suite_names=[
        "mmlu_redux_gen_5_shot_str",
        "telequad_gen_0_shot",
    ])
    session.commit()
    t = session.query(Task).filter_by(key="telequad_gen_0_shot").one()
    assert t.type == "generic"
    assert t.is_llm_judge is True  # telequad_gen_0_shot 是 LLM judge 任务


def test_seed_custom_tasks(session):
    seed_custom_tasks(session, task_nums=[1, 34, 36])
    session.commit()
    t = session.query(Task).filter_by(key="task_34_suite").one()
    assert t.type == "custom"
    assert t.custom_task_num == 34
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_seed.py -v`
Expected: FAIL

- [ ] **Step 3: 写 seed.py**

创建 `backend/app/services/__init__.py`（空）。
创建 `backend/app/services/seed.py`:
```python
from pathlib import Path
from sqlalchemy.orm import Session

from backend.app.models import Task


AIS_BENCH_CONFIGS = Path(__file__).resolve().parents[3] / \
    "ais_bench" / "benchmark" / "configs" / "datasets"


def _detect_is_llm_judge(suite_name: str) -> bool:
    """扫描 suite 配置文件，判断是否使用 LLMJudgeEvaluator。"""
    for py in AIS_BENCH_CONFIGS.rglob(f"{suite_name}.py"):
        try:
            if "LLMJudgeEvaluator" in py.read_text(encoding="utf-8"):
                return True
        except Exception:
            pass
    return False


def seed_generic_tasks(session: Session, suite_names: list[str]):
    for suite in suite_names:
        if session.query(Task).filter_by(key=suite).first():
            continue
        session.add(Task(
            key=suite,
            type="generic",
            suite_name=suite,
            display_name=suite,
            is_llm_judge=_detect_is_llm_judge(suite),
        ))


def seed_custom_tasks(session: Session, task_nums: list[int]):
    for num in task_nums:
        key = f"task_{num}_suite"
        if session.query(Task).filter_by(key=key).first():
            continue
        session.add(Task(
            key=key,
            type="custom",
            suite_name=key,
            display_name=f"Custom Task {num}",
            custom_task_num=num,
            default_data_rel_path=f"data/custom_task/task_{num}.jsonl",
            is_llm_judge=_detect_is_llm_judge(key),
        ))
```

- [ ] **Step 4: 写 CLI 入口**

创建 `backend/scripts/__init__.py`（空）。
创建 `backend/scripts/seed_tasks.py`:
```python
"""从现有配置种植 Task 表。用法：python -m backend.scripts.seed_tasks"""
from backend.app.db import get_session, init_db
from backend.app.services.seed import seed_generic_tasks, seed_custom_tasks


# 与 run_mixed_benchmark.sh 保持一致的默认任务集
DEFAULT_GENERIC = [
    "ceval_gen_0_shot_str", "mmlu_redux_gen_5_shot_str", "teledata_gen_0_shot",
    "gpqa_gen_0_shot_str", "bbh_gen_3_shot_cot_chat", "BFCL_gen_simple",
    "ifeval_0_shot_gen_str", "math500_gen_0_shot_cot_chat_prompt",
    "aime2025_gen_0_shot_chat_prompt", "telemath_gen_0_cot_shot",
    "teleqna_gen_0_shot", "tspec_gen_0_shot", "telequad_gen_0_shot",
    "tele_exam_gen_0_shot", "tele_exam_gen_0_shot_str", "opseval_gen_0_shot",
    "identity_gen_0_shot", "exam_gen_0_shot",
]
DEFAULT_CUSTOM = [1, 34, 36, 43, 44, 60]


def main():
    init_db()
    with get_session() as session:
        seed_generic_tasks(session, DEFAULT_GENERIC)
        seed_custom_tasks(session, DEFAULT_CUSTOM)
        session.commit()
    print("Seeded tasks.")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: 验证测试通过**

Run: `cd backend && pytest tests/test_seed.py -v`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add backend/app/services/ backend/scripts/ backend/tests/test_seed.py
git commit -m "feat(backend): 任务种子初始化 + CLI"
```

---

### P0-Task 4: Model CRUD API

**Files:**
- Create: `backend/app/schemas.py`
- Create: `backend/app/deps.py`
- Create: `backend/app/routers/__init__.py`
- Create: `backend/app/routers/models.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_models_api.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/conftest.py`:
```python
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.app import db as db_mod
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
    yield


@pytest.fixture
def client():
    return TestClient(app)
```

创建 `backend/tests/test_models_api.py`:
```python
def test_create_model(client):
    payload = {
        "name": "qwen32b",
        "host": "10.0.0.1",
        "port": 9092,
        "model_name": "qwen3-32b",
        "concurrency": 20,
    }
    r = client.post("/api/v1/models", json=payload)
    assert r.status_code == 201
    body = r.json()
    assert body["id"] > 0
    assert body["name"] == "qwen32b"


def test_list_models(client):
    client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"})
    r = client.get("/api/v1/models")
    assert r.status_code == 200
    assert len(r.json()) == 1


def test_duplicate_name_rejected(client):
    p = {"name": "dup", "host": "h", "port": 1, "model_name": "x"}
    client.post("/api/v1/models", json=p)
    r = client.post("/api/v1/models", json=p)
    assert r.status_code == 409
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_models_api.py -v`
Expected: FAIL（404，router 未挂）

- [ ] **Step 3: 写 schemas 和 deps**

创建 `backend/app/schemas.py`:
```python
from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict


class ModelCreate(BaseModel):
    name: str
    host: str
    port: int
    model_name: str
    concurrency: int = 20
    gen_kwargs_json: dict[str, Any] = {}
    model_config_key: str = "local_qwen"


class ModelUpdate(BaseModel):
    host: str | None = None
    port: int | None = None
    model_name: str | None = None
    concurrency: int | None = None
    gen_kwargs_json: dict[str, Any] | None = None
    model_config_key: str | None = None


class ModelOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    host: str
    port: int
    model_name: str
    concurrency: int
    gen_kwargs_json: dict[str, Any]
    model_config_key: str
    created_at: datetime
    updated_at: datetime
```

创建 `backend/app/deps.py`:
```python
from typing import Generator
from sqlalchemy.orm import Session

from backend.app.db import get_session


def db_session() -> Generator[Session, None, None]:
    session = get_session()
    try:
        yield session
    finally:
        session.close()
```

- [ ] **Step 4: 写 models router**

创建 `backend/app/routers/__init__.py`（空）。
创建 `backend/app/routers/models.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.deps import db_session
from backend.app.models import Model
from backend.app.schemas import ModelCreate, ModelOut, ModelUpdate


router = APIRouter(prefix="/api/v1/models", tags=["models"])


@router.post("", response_model=ModelOut, status_code=status.HTTP_201_CREATED)
def create(payload: ModelCreate, db: Session = Depends(db_session)):
    m = Model(**payload.model_dump())
    db.add(m)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "name already exists")
    db.refresh(m)
    return m


@router.get("", response_model=list[ModelOut])
def list_(db: Session = Depends(db_session)):
    return db.query(Model).order_by(Model.id).all()


@router.get("/{mid}", response_model=ModelOut)
def get(mid: int, db: Session = Depends(db_session)):
    m = db.get(Model, mid)
    if not m:
        raise HTTPException(404)
    return m


@router.put("/{mid}", response_model=ModelOut)
def update(mid: int, payload: ModelUpdate, db: Session = Depends(db_session)):
    m = db.get(Model, mid)
    if not m:
        raise HTTPException(404)
    for k, v in payload.model_dump(exclude_none=True).items():
        setattr(m, k, v)
    db.commit()
    db.refresh(m)
    return m


@router.delete("/{mid}", status_code=204)
def delete(mid: int, db: Session = Depends(db_session)):
    m = db.get(Model, mid)
    if not m:
        raise HTTPException(404)
    db.delete(m)
    db.commit()
```

- [ ] **Step 5: 挂载 router**

Modify `backend/app/main.py`:
```python
from fastapi import FastAPI
from contextlib import asynccontextmanager

from backend.app.db import init_db
from backend.app.routers import models as models_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Eval Backend", version="0.1.0", lifespan=lifespan)
app.include_router(models_router.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: 验证测试通过**

Run: `cd backend && pytest tests/test_models_api.py -v`
Expected: PASS（3 passed）

- [ ] **Step 7: 提交**

```bash
git add backend/
git commit -m "feat(backend): Model CRUD API"
```

---

### P0-Task 5: JudgeLLM CRUD API

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routers/judges.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_judges_api.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_judges_api.py`:
```python
def test_create_judge(client):
    payload = {
        "name": "judge-qwen-plus",
        "host": "dashscope",
        "port": 443,
        "model_name": "qwen-plus",
    }
    r = client.post("/api/v1/judges", json=payload)
    assert r.status_code == 201
    assert r.json()["name"] == "judge-qwen-plus"


def test_list_judges(client):
    client.post("/api/v1/judges", json={
        "name": "j1", "host": "h", "port": 1, "model_name": "x"})
    r = client.get("/api/v1/judges")
    assert len(r.json()) == 1
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_judges_api.py -v`
Expected: FAIL

- [ ] **Step 3: 复用 Model CRUD 模板为 Judge 实现**

在 `backend/app/schemas.py` 追加 `JudgeCreate/Update/Out`（字段参考 `JudgeLLM` 模型）。
创建 `backend/app/routers/judges.py`，结构与 `models.py` 一致，将 `Model` 替换为 `JudgeLLM`，prefix 改为 `/api/v1/judges`。

Modify `backend/app/main.py`，追加：
```python
from backend.app.routers import judges as judges_router
app.include_router(judges_router.router)
```

- [ ] **Step 4: 验证测试通过**

Run: `cd backend && pytest tests/test_judges_api.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/
git commit -m "feat(backend): JudgeLLM CRUD API"
```

---

### P0-Task 6: Task 只读 API

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routers/tasks.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_tasks_api.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_tasks_api.py`:
```python
from backend.app.db import get_session
from backend.app.services.seed import seed_generic_tasks, seed_custom_tasks


def _seed():
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        seed_custom_tasks(s, [34])
        s.commit()


def test_list_tasks(client):
    _seed()
    r = client.get("/api/v1/tasks")
    assert r.status_code == 200
    items = r.json()
    assert len(items) == 2
    keys = {t["key"] for t in items}
    assert keys == {"mmlu_redux_gen_5_shot_str", "task_34_suite"}


def test_get_task(client):
    _seed()
    r = client.get("/api/v1/tasks")
    tid = r.json()[0]["id"]
    r2 = client.get(f"/api/v1/tasks/{tid}")
    assert r2.status_code == 200
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_tasks_api.py -v`
Expected: FAIL

- [ ] **Step 3: 写 TaskOut schema 和 router**

在 `backend/app/schemas.py` 追加：
```python
class TaskOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    key: str
    type: str
    suite_name: str
    display_name: str | None
    custom_task_num: int | None
    default_data_rel_path: str | None
    is_llm_judge: bool
```

创建 `backend/app/routers/tasks.py`:
```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.deps import db_session
from backend.app.models import Task
from backend.app.schemas import TaskOut


router = APIRouter(prefix="/api/v1/tasks", tags=["tasks"])


@router.get("", response_model=list[TaskOut])
def list_(db: Session = Depends(db_session)):
    return db.query(Task).order_by(Task.key).all()


@router.get("/{tid}", response_model=TaskOut)
def get(tid: int, db: Session = Depends(db_session)):
    t = db.get(Task, tid)
    if not t:
        raise HTTPException(404)
    return t
```

挂载到 main.py。

- [ ] **Step 4: 验证测试通过**

Run: `cd backend && pytest tests/test_tasks_api.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/
git commit -m "feat(backend): Task 只读 API"
```

---

### P0-Task 7: Batch 创建 API + 初始 Revision

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/services/batch_service.py`
- Create: `backend/app/routers/batches.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_batch_create.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_batch_create.py`:
```python
from backend.app.db import get_session
from backend.app.models import BatchCell, BatchRevision, Job
from backend.app.services.seed import seed_generic_tasks


def _prep(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    m = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()
    t = client.get("/api/v1/tasks").json()[0]
    return m["id"], t["id"]


def test_create_batch_generates_cells_jobs_revision(client):
    mid, tid = _prep(client)
    r = client.post("/api/v1/batches", json={
        "name": "round-1",
        "mode": "all",
        "model_ids": [mid],
        "task_ids": [tid],
    })
    assert r.status_code == 201
    bid = r.json()["id"]

    with get_session() as s:
        cells = s.query(BatchCell).filter_by(batch_id=bid).all()
        assert len(cells) == 1
        revs = s.query(BatchRevision).filter_by(batch_id=bid).all()
        assert len(revs) == 1
        assert revs[0].rev_num == 1
        assert revs[0].change_type == "create"
        jobs = s.query(Job).filter_by(batch_id=bid).all()
        # mode=all: 每 cell 一个 infer + 一个 eval
        assert len(jobs) == 2
        types = sorted(j.type for j in jobs)
        assert types == ["eval", "infer"]


def test_create_batch_mode_infer_only_creates_infer_jobs(client):
    mid, tid = _prep(client)
    r = client.post("/api/v1/batches", json={
        "name": "infer-only",
        "mode": "infer",
        "model_ids": [mid],
        "task_ids": [tid],
    })
    bid = r.json()["id"]
    with get_session() as s:
        jobs = s.query(Job).filter_by(batch_id=bid).all()
        assert len(jobs) == 1
        assert jobs[0].type == "infer"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_batch_create.py -v`
Expected: FAIL

- [ ] **Step 3: 写 Batch schema**

在 `backend/app/schemas.py` 追加：
```python
class BatchCreate(BaseModel):
    name: str
    mode: str = "all"  # infer | eval | all
    model_ids: list[int]
    task_ids: list[int]
    default_eval_version: str = "eval_init"
    default_judge_id: int | None = None
    notes: str | None = None


class BatchOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    name: str
    mode: str
    default_eval_version: str
    default_judge_id: int | None
    notes: str | None
    created_at: datetime
    updated_at: datetime
```

- [ ] **Step 4: 写 batch_service**

创建 `backend/app/services/batch_service.py`:
```python
from sqlalchemy.orm import Session

from backend.app.models import (
    Batch, BatchCell, BatchRevision, Job, Model, Task,
)


def _snapshot(db: Session, batch_id: int) -> dict:
    cells = db.query(BatchCell).filter_by(batch_id=batch_id).all()
    return {
        "cells": [
            {
                "model_id": c.model_id,
                "task_id": c.task_id,
                "dataset_version_id": c.dataset_version_id,
                "current_prediction_id": c.current_prediction_id,
                "current_evaluation_id": c.current_evaluation_id,
            }
            for c in cells
        ]
    }


def _next_rev_num(db: Session, batch_id: int) -> int:
    last = (
        db.query(BatchRevision.rev_num)
        .filter_by(batch_id=batch_id)
        .order_by(BatchRevision.rev_num.desc())
        .first()
    )
    return (last[0] + 1) if last else 1


def record_revision(
    db: Session, batch_id: int, change_type: str, change_summary: str
):
    rev = BatchRevision(
        batch_id=batch_id,
        rev_num=_next_rev_num(db, batch_id),
        change_type=change_type,
        change_summary=change_summary,
        snapshot_json=_snapshot(db, batch_id),
    )
    db.add(rev)


def create_batch(db: Session, payload) -> Batch:
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
    )
    db.add(batch)
    db.flush()

    # 生成 N×M 个 cells
    for m in models:
        for t in tasks:
            db.add(BatchCell(
                batch_id=batch.id, model_id=m.id, task_id=t.id,
            ))
    db.flush()

    # 生成 jobs
    for m in models:
        for t in tasks:
            infer_job = None
            if payload.mode in ("infer", "all"):
                infer_job = Job(
                    type="infer", batch_id=batch.id,
                    model_id=m.id, task_id=t.id,
                    params_json={},
                )
                db.add(infer_job)
                db.flush()
            if payload.mode in ("eval", "all"):
                eval_job = Job(
                    type="eval", batch_id=batch.id,
                    model_id=m.id, task_id=t.id,
                    params_json={"eval_version": batch.default_eval_version},
                    dependency_job_id=infer_job.id if infer_job else None,
                )
                db.add(eval_job)

    record_revision(db, batch.id, "create", f"create batch '{batch.name}'")
    return batch
```

- [ ] **Step 5: 写 batches router**

创建 `backend/app/routers/batches.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from backend.app.deps import db_session
from backend.app.models import Batch
from backend.app.schemas import BatchCreate, BatchOut
from backend.app.services.batch_service import create_batch


router = APIRouter(prefix="/api/v1/batches", tags=["batches"])


@router.post("", response_model=BatchOut, status_code=status.HTTP_201_CREATED)
def create(payload: BatchCreate, db: Session = Depends(db_session)):
    try:
        batch = create_batch(db, payload)
    except ValueError as e:
        raise HTTPException(400, str(e))
    db.commit()
    db.refresh(batch)
    return batch


@router.get("", response_model=list[BatchOut])
def list_(db: Session = Depends(db_session)):
    return db.query(Batch).order_by(Batch.id.desc()).all()


@router.get("/{bid}", response_model=BatchOut)
def get(bid: int, db: Session = Depends(db_session)):
    b = db.get(Batch, bid)
    if not b:
        raise HTTPException(404)
    return b
```

挂载到 main.py。

- [ ] **Step 6: 验证测试通过**

Run: `cd backend && pytest tests/test_batch_create.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/
git commit -m "feat(backend): Batch 创建 + 自动生成 cells/jobs/revision"
```

---

### P0-Task 8: Docker 命令拼装器

**Files:**
- Create: `backend/app/services/docker_runner.py`
- Create: `backend/tests/test_docker_runner.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_docker_runner.py`:
```python
from pathlib import Path

from backend.app.services.docker_runner import build_infer_cmd, build_eval_cmd


def _settings(tmp_path):
    from backend.app.config import Settings
    return Settings(
        backend_data_dir=tmp_path / "bd",
        workspace_dir=tmp_path / "ws",
        code_dir=tmp_path / "ws" / "code",
        docker_image_tag="benchmark-eval:latest",
    )


def test_build_infer_cmd_custom_task(tmp_path):
    s = _settings(tmp_path)
    cmd = build_infer_cmd(
        settings=s,
        job_id=42,
        env_file=tmp_path / "env",
        output_task_id="mixed_eval_xyz",
        model_config_key="local_qwen",
        task_type="custom",
        custom_task_num=34,
        suite_name="task_34_suite",
    )
    assert "docker" in cmd[0]
    assert "run" in cmd
    assert "--env-file" in cmd
    assert str(tmp_path / "env") in cmd
    assert "--tasks" in cmd
    assert "34" in cmd
    assert "python" in cmd
    assert "eval_entry.py" in cmd


def test_build_infer_cmd_generic(tmp_path):
    s = _settings(tmp_path)
    cmd = build_infer_cmd(
        settings=s, job_id=1, env_file=tmp_path/"e",
        output_task_id="t", model_config_key="local_qwen",
        task_type="generic", custom_task_num=None,
        suite_name="mmlu_redux_gen_5_shot_str",
    )
    assert "--generic-datasets" in cmd
    assert "mmlu_redux_gen_5_shot_str" in cmd


def test_build_eval_cmd(tmp_path):
    s = _settings(tmp_path)
    cmd = build_eval_cmd(
        settings=s, job_id=3, env_file=tmp_path/"e",
        output_task_id="mixed_eval_xyz",
        eval_version="eval_v2",
        suite_name="task_34_suite",
    )
    assert "eval_judge.py" in cmd
    assert "--infer-task" in cmd
    assert "mixed_eval_xyz" in cmd
    assert "--eval-version" in cmd
    assert "eval_v2" in cmd
    assert "--eval-tasks" in cmd
    assert "task_34_suite" in cmd
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_docker_runner.py -v`
Expected: FAIL

- [ ] **Step 3: 写 docker_runner**

创建 `backend/app/services/docker_runner.py`:
```python
from pathlib import Path

from backend.app.config import Settings


def _common_docker_args(settings: Settings, job_id: int,
                        env_file: Path, container_name: str) -> list[str]:
    return [
        "docker", "run", "--rm",
        "--name", container_name,
        "--memory=128g", "--memory-swap=128g", "--shm-size=16g",
        "--env-file", str(env_file),
        "-v", f"{settings.workspace_dir}/data:/app/data",
        "-v", f"{settings.workspace_dir}/outputs:/app/outputs",
        "-v", f"{settings.code_dir}/eval_entry.py:/app/eval_entry.py",
        "-v", f"{settings.code_dir}/eval_judge.py:/app/eval_judge.py",
        "-v", f"{settings.code_dir}/scripts:/app/scripts",
        settings.docker_image_tag,
    ]


def build_infer_cmd(
    settings: Settings,
    job_id: int,
    env_file: Path,
    output_task_id: str,
    model_config_key: str,
    task_type: str,          # 'custom' | 'generic'
    custom_task_num: int | None,
    suite_name: str,
) -> list[str]:
    cmd = _common_docker_args(
        settings, job_id, env_file, f"eval-{job_id}-infer"
    )
    cmd += [
        "python", "eval_entry.py",
        "--task-id", output_task_id,
        "--model-config", model_config_key,
    ]
    if task_type == "custom":
        cmd += ["--tasks", str(custom_task_num)]
    else:
        cmd += ["--generic-datasets", suite_name]
    return cmd


def build_eval_cmd(
    settings: Settings,
    job_id: int,
    env_file: Path,
    output_task_id: str,
    eval_version: str,
    suite_name: str,
) -> list[str]:
    cmd = _common_docker_args(
        settings, job_id, env_file, f"eval-{job_id}-judge"
    )
    cmd += [
        "python", "eval_judge.py",
        "--infer-task", output_task_id,
        "--eval-version", eval_version,
        "--eval-tasks", suite_name,
    ]
    return cmd


def write_env_file(settings: Settings, job_id: int,
                   env_vars: dict[str, str]) -> Path:
    settings.envs_dir.mkdir(parents=True, exist_ok=True)
    path = settings.envs_dir / f"job_{job_id}.env"
    lines = [f"{k}={v}" for k, v in env_vars.items()]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
```

- [ ] **Step 4: 验证测试通过**

Run: `cd backend && pytest tests/test_docker_runner.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/docker_runner.py backend/tests/test_docker_runner.py
git commit -m "feat(backend): docker 命令拼装器"
```

---

### P0-Task 9: Worker 主循环（核心）

**Files:**
- Create: `backend/app/services/worker.py`
- Create: `backend/tests/test_worker.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: 写失败测试（mock subprocess）**

创建 `backend/tests/test_worker.py`:
```python
import asyncio
from unittest.mock import patch, MagicMock

import pytest

from backend.app.db import get_session
from backend.app.models import Job, Model, Task
from backend.app.services.worker import run_pending_jobs_once
from backend.app.services.seed import seed_generic_tasks


async def _seed(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    mid = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()["id"]
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    r = client.post("/api/v1/batches", json={
        "name": "b1", "mode": "infer",
        "model_ids": [mid], "task_ids": [tid],
    })
    return r.json()["id"], mid, tid


async def test_worker_picks_and_runs_pending_job(client):
    bid, mid, tid = await _seed(client)

    fake_proc = MagicMock()
    fake_proc.pid = 12345
    fake_proc.returncode = 0
    fake_proc.wait.return_value = 0

    with patch(
        "backend.app.services.worker.subprocess.Popen",
        return_value=fake_proc,
    ) as popen, patch(
        "backend.app.services.worker.scan_infer_output",
        return_value={"output_path": "/tmp", "num_samples": 100},
    ):
        await run_pending_jobs_once()

    with get_session() as s:
        job = s.query(Job).filter_by(batch_id=bid).first()
        assert job.status == "success"
        assert job.returncode == 0
        popen.assert_called_once()
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_worker.py -v`
Expected: FAIL

- [ ] **Step 3: 写 worker.py 骨架**

创建 `backend/app/services/worker.py`:
```python
import asyncio
import subprocess
from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from backend.app.config import get_settings
from backend.app.db import get_session
from backend.app.models import (
    Batch, BatchCell, Job, Model, Prediction, Evaluation, Task,
)
from backend.app.services.batch_service import record_revision
from backend.app.services.docker_runner import (
    build_eval_cmd, build_infer_cmd, write_env_file,
)
from backend.app.services.scan import scan_infer_output, scan_eval_output


def _pick_next_job(db: Session) -> Job | None:
    # 先跑 infer（无依赖），再跑 eval（依赖已完成）
    q = db.query(Job).filter(Job.status == "pending")
    for job in q.order_by(Job.id).all():
        if job.dependency_job_id:
            dep = db.get(Job, job.dependency_job_id)
            if dep.status != "success":
                continue
        return job
    return None


def _env_vars_for_model(model: Model) -> dict[str, str]:
    return {
        "LOCAL_MODEL_NAME": model.model_name,
        "LOCAL_HOST_IP": model.host,
        "LOCAL_HOST_PORT": str(model.port),
        "LOCAL_CONCURRENCY": str(model.concurrency),
        "PYTHONUNBUFFERED": "1",
    }


def _make_output_task_id(job: Job) -> str:
    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    return f"batch{job.batch_id}_m{job.model_id}_t{job.task_id}_{ts}"


def _run_infer(db: Session, job: Job, settings):
    model = db.get(Model, job.model_id)
    task = db.get(Task, job.task_id)

    output_task_id = _make_output_task_id(job)
    env_file = write_env_file(settings, job.id, _env_vars_for_model(model))
    cmd = build_infer_cmd(
        settings=settings, job_id=job.id, env_file=env_file,
        output_task_id=output_task_id,
        model_config_key=model.model_config_key,
        task_type=task.type,
        custom_task_num=task.custom_task_num,
        suite_name=task.suite_name,
    )

    log_path = settings.logs_dir / f"job_{job.id}.log"
    settings.logs_dir.mkdir(parents=True, exist_ok=True)

    job.params_json = {**(job.params_json or {}), "output_task_id": output_task_id}
    job.status = "running"
    job.started_at = datetime.utcnow()
    job.log_path = str(log_path)
    db.commit()

    with open(log_path, "wb") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
        job.pid = proc.pid
        db.commit()
        returncode = proc.wait()

    job.returncode = returncode
    job.finished_at = datetime.utcnow()

    if returncode == 0:
        info = scan_infer_output(settings, output_task_id, task.suite_name)
        pred = Prediction(
            model_id=job.model_id, task_id=job.task_id,
            dataset_version_id=None,
            status="success",
            output_task_id=output_task_id,
            output_path=info["output_path"],
            num_samples=info["num_samples"],
            duration_sec=(job.finished_at - job.started_at).total_seconds(),
            job_id=job.id, finished_at=job.finished_at,
        )
        db.add(pred)
        db.flush()
        job.produces_prediction_id = pred.id
        job.status = "success"

        if job.batch_id:
            cell = db.get(BatchCell, (job.batch_id, job.model_id, job.task_id))
            if cell:
                cell.current_prediction_id = pred.id
                record_revision(
                    db, job.batch_id, "infer_done",
                    f"prediction {pred.id} for model={job.model_id} task={job.task_id}",
                )
    else:
        job.status = "failed"
    db.commit()


def _run_eval(db: Session, job: Job, settings):
    if job.dependency_job_id:
        dep = db.get(Job, job.dependency_job_id)
        prediction = db.get(Prediction, dep.produces_prediction_id)
    else:
        cell = db.get(BatchCell, (job.batch_id, job.model_id, job.task_id))
        prediction = db.get(Prediction, cell.current_prediction_id) if cell else None
    if not prediction:
        job.status = "failed"
        job.error_msg = "no prediction to evaluate"
        db.commit()
        return

    model = db.get(Model, job.model_id)
    task = db.get(Task, job.task_id)
    eval_version = job.params_json.get("eval_version", "eval_init")
    env_file = write_env_file(settings, job.id, _env_vars_for_model(model))
    cmd = build_eval_cmd(
        settings=settings, job_id=job.id, env_file=env_file,
        output_task_id=prediction.output_task_id,
        eval_version=eval_version,
        suite_name=task.suite_name,
    )

    log_path = settings.logs_dir / f"job_{job.id}.log"
    job.status = "running"
    job.started_at = datetime.utcnow()
    job.log_path = str(log_path)
    db.commit()

    with open(log_path, "wb") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
        job.pid = proc.pid
        db.commit()
        returncode = proc.wait()

    job.returncode = returncode
    job.finished_at = datetime.utcnow()

    if returncode == 0:
        info = scan_eval_output(settings, prediction.output_task_id, eval_version,
                                task.suite_name)
        ev = Evaluation(
            prediction_id=prediction.id, eval_version=eval_version,
            status="success", accuracy=info["accuracy"],
            details_path=info["details_path"],
            num_samples=info["num_samples"],
            duration_sec=(job.finished_at - job.started_at).total_seconds(),
            job_id=job.id, finished_at=job.finished_at,
        )
        db.add(ev)
        db.flush()
        job.produces_evaluation_id = ev.id
        job.status = "success"

        if job.batch_id:
            cell = db.get(BatchCell, (job.batch_id, job.model_id, job.task_id))
            if cell:
                cell.current_evaluation_id = ev.id
                record_revision(
                    db, job.batch_id, "eval_done",
                    f"evaluation {ev.id} for model={job.model_id} task={job.task_id}",
                )
    else:
        job.status = "failed"
    db.commit()


async def run_pending_jobs_once():
    settings = get_settings()
    with get_session() as db:
        job = _pick_next_job(db)
        if not job:
            return
    # 独立 session 执行避免长事务
    with get_session() as db:
        job = db.get(Job, job.id)
        if job.type == "infer":
            _run_infer(db, job, settings)
        else:
            _run_eval(db, job, settings)


async def worker_loop():
    settings = get_settings()
    while True:
        try:
            await run_pending_jobs_once()
        except Exception as e:
            print(f"[worker] error: {e}")
        await asyncio.sleep(settings.worker_poll_interval_sec)
```

- [ ] **Step 4: 写 scan.py 占位（Task 10 会填充）**

创建 `backend/app/services/scan.py`:
```python
from pathlib import Path

from backend.app.config import Settings


def scan_infer_output(settings: Settings, output_task_id: str,
                      suite_name: str) -> dict:
    """扫描 outputs/{output_task_id}/ 得到推理产物信息。"""
    root = settings.workspace_dir / "outputs" / output_task_id
    # Task 10 会实现正式扫描；这里返回最小信息
    return {
        "output_path": str(root),
        "num_samples": None,
    }


def scan_eval_output(settings: Settings, output_task_id: str,
                     eval_version: str, suite_name: str) -> dict:
    """扫描评测产物得到 accuracy。"""
    details_dir = (settings.workspace_dir / "outputs" / output_task_id
                   / eval_version / suite_name)
    return {
        "accuracy": None,
        "details_path": str(details_dir),
        "num_samples": None,
    }
```

- [ ] **Step 5: main.py 启动 Worker**

Modify `backend/app/main.py`：
```python
import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from backend.app.db import init_db
from backend.app.routers import batches as batches_router
from backend.app.routers import judges as judges_router
from backend.app.routers import models as models_router
from backend.app.routers import tasks as tasks_router
from backend.app.services.worker import worker_loop


_worker_task = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _worker_task
    init_db()
    _worker_task = asyncio.create_task(worker_loop())
    yield
    _worker_task.cancel()


app = FastAPI(title="Eval Backend", version="0.1.0", lifespan=lifespan)
app.include_router(models_router.router)
app.include_router(judges_router.router)
app.include_router(tasks_router.router)
app.include_router(batches_router.router)


@app.get("/api/v1/health")
def health():
    return {"status": "ok"}
```

- [ ] **Step 6: 验证测试通过**

Run: `cd backend && pytest tests/test_worker.py -v`
Expected: PASS

- [ ] **Step 7: 提交**

```bash
git add backend/
git commit -m "feat(backend): Worker 主循环 + 推理/评测执行"
```

---

### P0-Task 10: 产物扫描 scan.py 实现

**Files:**
- Modify: `backend/app/services/scan.py`
- Create: `backend/tests/test_scan.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_scan.py`:
```python
import json
from pathlib import Path

from backend.app.config import Settings
from backend.app.services.scan import scan_infer_output, scan_eval_output


def _make_settings(tmp_path):
    return Settings(backend_data_dir=tmp_path/"bd",
                    workspace_dir=tmp_path/"ws",
                    code_dir=tmp_path/"ws/code")


def test_scan_infer_output_reads_infer_meta(tmp_path):
    s = _make_settings(tmp_path)
    task_id = "abc"
    d = s.workspace_dir / "outputs" / task_id
    d.mkdir(parents=True)
    (d / "infer_meta.json").write_text(json.dumps({
        "model_config": "local_qwen",
        "tasks": [{"suite": "task_34_suite", "num_samples": 500}],
    }))
    info = scan_infer_output(s, task_id, "task_34_suite")
    assert info["num_samples"] == 500
    assert info["output_path"] == str(d)


def test_scan_eval_output_reads_summary(tmp_path):
    s = _make_settings(tmp_path)
    task_id = "abc"
    eval_ver = "eval_v2"
    suite = "task_34_suite"
    eval_dir = s.workspace_dir / "outputs" / task_id / eval_ver / suite
    eval_dir.mkdir(parents=True)
    (eval_dir / "summary.json").write_text(json.dumps({
        "accuracy": 87.5, "num_samples": 500,
    }))
    info = scan_eval_output(s, task_id, eval_ver, suite)
    assert info["accuracy"] == 87.5
    assert info["num_samples"] == 500
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_scan.py -v`
Expected: FAIL

- [ ] **Step 3: 实现 scan.py**

Modify `backend/app/services/scan.py`:
```python
import json
from pathlib import Path

from backend.app.config import Settings


def scan_infer_output(settings: Settings, output_task_id: str,
                      suite_name: str) -> dict:
    root = settings.workspace_dir / "outputs" / output_task_id
    num_samples = None
    meta = root / "infer_meta.json"
    if meta.exists():
        try:
            data = json.loads(meta.read_text(encoding="utf-8"))
            for t in data.get("tasks", []):
                if t.get("suite") == suite_name:
                    num_samples = t.get("num_samples")
                    break
        except Exception:
            pass
    return {"output_path": str(root), "num_samples": num_samples}


def scan_eval_output(settings: Settings, output_task_id: str,
                     eval_version: str, suite_name: str) -> dict:
    details_dir = (settings.workspace_dir / "outputs" / output_task_id
                   / eval_version / suite_name)
    accuracy = None
    num_samples = None
    for fname in ("summary.json", "report.json"):
        p = details_dir / fname
        if not p.exists():
            continue
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            accuracy = data.get("accuracy", accuracy)
            num_samples = data.get("num_samples", num_samples)
        except Exception:
            pass
    return {"accuracy": accuracy, "details_path": str(details_dir),
            "num_samples": num_samples}
```

> 注意：实际产物文件的键可能与 `eval_judge.py` 输出不一致，实施时需对齐 `eval_judge.py` 实际产出格式（参考 `my_doc/deploy.md` 的 report.json 示例）。如有偏差，同步修改本函数。

- [ ] **Step 4: 验证测试通过**

Run: `cd backend && pytest tests/test_scan.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/app/services/scan.py backend/tests/test_scan.py
git commit -m "feat(backend): 产物扫描支持 infer_meta.json 与 summary.json"
```

---

### P0-Task 11: 战报 API

**Files:**
- Modify: `backend/app/schemas.py`
- Modify: `backend/app/routers/batches.py`
- Create: `backend/tests/test_batch_report.py`

- [ ] **Step 1: 写失败测试**

创建 `backend/tests/test_batch_report.py`:
```python
from backend.app.db import get_session
from backend.app.models import BatchCell, Evaluation, Prediction, Task
from backend.app.services.seed import seed_generic_tasks


def test_report_shows_matrix(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    mid = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()["id"]
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    bid = client.post("/api/v1/batches", json={
        "name": "b", "mode": "all",
        "model_ids": [mid], "task_ids": [tid]}).json()["id"]

    # 模拟 worker 完成
    with get_session() as s:
        pred = Prediction(model_id=mid, task_id=tid, status="success",
                          output_task_id="tx", output_path="/p",
                          num_samples=10)
        s.add(pred); s.flush()
        ev = Evaluation(prediction_id=pred.id, eval_version="eval_init",
                        status="success", accuracy=88.0, num_samples=10)
        s.add(ev); s.flush()
        cell = s.get(BatchCell, (bid, mid, tid))
        cell.current_prediction_id = pred.id
        cell.current_evaluation_id = ev.id
        s.commit()

    r = client.get(f"/api/v1/batches/{bid}/report")
    assert r.status_code == 200
    body = r.json()
    assert body["batch_id"] == bid
    assert len(body["rows"]) == 1
    row = body["rows"][0]
    assert row["model_id"] == mid
    assert row["task_id"] == tid
    assert row["accuracy"] == 88.0
    assert row["num_samples"] == 10
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_batch_report.py -v`
Expected: FAIL

- [ ] **Step 3: 写 report 路由**

在 `backend/app/schemas.py` 追加：
```python
class BatchReportRow(BaseModel):
    model_id: int
    model_name: str
    task_id: int
    task_key: str
    prediction_id: int | None
    evaluation_id: int | None
    accuracy: float | None
    num_samples: int | None
    status: str


class BatchReport(BaseModel):
    batch_id: int
    batch_name: str
    generated_at: datetime
    rows: list[BatchReportRow]
```

Modify `backend/app/routers/batches.py`：
```python
from datetime import datetime

from backend.app.models import (
    Batch, BatchCell, Evaluation, Model, Prediction, Task,
)
from backend.app.schemas import BatchReport, BatchReportRow


@router.get("/{bid}/report", response_model=BatchReport)
def report(bid: int, db: Session = Depends(db_session)):
    batch = db.get(Batch, bid)
    if not batch:
        raise HTTPException(404)
    cells = db.query(BatchCell).filter_by(batch_id=bid).all()
    rows = []
    for c in cells:
        m = db.get(Model, c.model_id)
        t = db.get(Task, c.task_id)
        pred = db.get(Prediction, c.current_prediction_id) if c.current_prediction_id else None
        ev = db.get(Evaluation, c.current_evaluation_id) if c.current_evaluation_id else None
        status = "pending"
        if ev and ev.status == "success":
            status = "eval_done"
        elif pred and pred.status == "success":
            status = "infer_done"
        rows.append(BatchReportRow(
            model_id=m.id, model_name=m.name,
            task_id=t.id, task_key=t.key,
            prediction_id=pred.id if pred else None,
            evaluation_id=ev.id if ev else None,
            accuracy=ev.accuracy if ev else None,
            num_samples=(ev.num_samples if ev else (pred.num_samples if pred else None)),
            status=status,
        ))
    return BatchReport(batch_id=batch.id, batch_name=batch.name,
                       generated_at=datetime.utcnow(), rows=rows)
```

- [ ] **Step 4: 验证测试通过**

Run: `cd backend && pytest tests/test_batch_report.py -v`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add backend/
git commit -m "feat(backend): Batch 战报 API"
```

---

### P0-Task 12: Job 查询 API + P0 E2E 验证

**Files:**
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routers/jobs.py`
- Modify: `backend/app/main.py`
- Create: `backend/tests/test_jobs_api.py`
- Create: `backend/docs/p0_e2e.md`

- [ ] **Step 1: 写失败测试（Job 查询）**

创建 `backend/tests/test_jobs_api.py`:
```python
from backend.app.db import get_session
from backend.app.services.seed import seed_generic_tasks


def test_list_and_get_job(client):
    with get_session() as s:
        seed_generic_tasks(s, ["mmlu_redux_gen_5_shot_str"])
        s.commit()
    mid = client.post("/api/v1/models", json={
        "name": "m1", "host": "h", "port": 1, "model_name": "x"}).json()["id"]
    tid = client.get("/api/v1/tasks").json()[0]["id"]
    client.post("/api/v1/batches", json={
        "name": "b", "mode": "infer",
        "model_ids": [mid], "task_ids": [tid]})

    r = client.get("/api/v1/jobs")
    assert r.status_code == 200
    jobs = r.json()
    assert len(jobs) >= 1
    jid = jobs[0]["id"]
    r2 = client.get(f"/api/v1/jobs/{jid}")
    assert r2.status_code == 200
    assert r2.json()["type"] == "infer"
```

- [ ] **Step 2: 运行测试验证失败**

Run: `cd backend && pytest tests/test_jobs_api.py -v`
Expected: FAIL

- [ ] **Step 3: 写 JobOut 和 router**

在 `backend/app/schemas.py` 追加：
```python
class JobOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    type: str
    status: str
    batch_id: int | None
    model_id: int | None
    task_id: int | None
    pid: int | None
    returncode: int | None
    produces_prediction_id: int | None
    produces_evaluation_id: int | None
    dependency_job_id: int | None
    log_path: str | None
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_msg: str | None
```

创建 `backend/app/routers/jobs.py`:
```python
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.deps import db_session
from backend.app.models import Job
from backend.app.schemas import JobOut


router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("", response_model=list[JobOut])
def list_(db: Session = Depends(db_session),
          batch_id: int | None = Query(None),
          status: str | None = Query(None)):
    q = db.query(Job)
    if batch_id is not None:
        q = q.filter_by(batch_id=batch_id)
    if status is not None:
        q = q.filter_by(status=status)
    return q.order_by(Job.id.desc()).limit(200).all()


@router.get("/{jid}", response_model=JobOut)
def get(jid: int, db: Session = Depends(db_session)):
    j = db.get(Job, jid)
    if not j:
        raise HTTPException(404)
    return j
```

挂载到 main.py。

- [ ] **Step 4: 验证测试通过**

Run: `cd backend && pytest -v`
Expected: 全部 PASS

- [ ] **Step 5: 写 P0 E2E 验证文档**

创建 `backend/docs/p0_e2e.md`:
```markdown
# P0 端到端验证

前置：docker 镜像 benchmark-eval:latest 已存在；workspace 配置正确。

## 1. 启动后端

    cd backend
    pip install -e '.[dev]'
    python -m backend.scripts.seed_tasks
    EVAL_BACKEND_WORKSPACE_DIR=/opt/eval_workspace \
    EVAL_BACKEND_CODE_DIR=/opt/eval_workspace/code \
    uvicorn backend.app.main:app --host 0.0.0.0 --port 8080

## 2. 注册一个模型

    curl -X POST http://localhost:8080/api/v1/models \
      -H 'Content-Type: application/json' \
      -d '{"name":"qwen32b","host":"188.109.35.147","port":9092,"model_name":"qwen3-32b","concurrency":20}'

## 3. 查看任务

    curl http://localhost:8080/api/v1/tasks

## 4. 创建一个小批次（一个模型 × 一个任务 × 推理+评测）

    curl -X POST http://localhost:8080/api/v1/batches \
      -H 'Content-Type: application/json' \
      -d '{"name":"smoke-1","mode":"all","model_ids":[1],"task_ids":[1]}'

## 5. 观察 job 进度

    watch -n 2 'curl -s http://localhost:8080/api/v1/jobs?batch_id=1 | jq'

## 6. 查看战报

    curl http://localhost:8080/api/v1/batches/1/report | jq

## 验收标准

- `/api/v1/jobs` 状态从 pending → running → success
- `/api/v1/batches/1/report` 返回的 row 有 accuracy 值（数字）
- `backend_data/logs/job_{id}.log` 存在可查看
- `outputs/{output_task_id}/eval_{version}/` 下有实际产物
```

- [ ] **Step 6: 提交**

```bash
git add backend/
git commit -m "feat(backend): Job 查询 API + P0 E2E 验证脚本"
```

---

## P1：场景 2 与场景 4 支持

> 本节只列 Task 级目标和关键实现点。进入实施阶段时再细化到 Step。

### P1-Task 1: DatasetVersion 上传 API

**Files:** `backend/app/routers/tasks.py`, `backend/tests/test_datasets.py`

**目标：** 用户上传一个任务的新数据文件，后端校验格式、计算 hash、落盘到 `data/versions/{task_key}/{tag}/data.jsonl`，插入 `dataset_versions` 表。可选 `is_default=true` 切换默认版本。

**关键点：**
- `POST /api/v1/tasks/{id}/datasets` multipart 上传 + form 字段 `tag`、`is_default`
- 校验：必须是 JSONL、首行可解析
- hash：SHA256 of 文件内容
- 新版本不自动激活，需要用户显式设 `is_default` 或在 rerun 时指定
- `GET /api/v1/tasks/{id}/datasets` 列出所有版本

### P1-Task 2: Docker 挂载数据版本

**Files:** `backend/app/services/docker_runner.py`, `backend/app/services/worker.py`

**目标：** 当 Prediction 绑定了非 default 的 `dataset_version_id`，Worker 在 `docker run` 时追加额外 `-v` 挂载，覆盖容器内的 `data/custom_task/task_N.jsonl`，并透传 `--data-dir` 给 `eval_entry.py`。

**关键点：**
- `build_infer_cmd` 追加 `override_data_path` 参数
- 软链/bind mount：`-v {version_path}:/app/data/custom_task_override/task_N.jsonl`
- `eval_entry.py --data-dir` 已原生支持指定数据目录

### P1-Task 3: Batch Rerun API（核心）

**Files:** `backend/app/services/batch_service.py`, `backend/app/routers/batches.py`, `backend/tests/test_batch_rerun.py`

**目标：** `POST /api/v1/batches/{id}/rerun` 接受 `{model_ids, task_ids, what: infer|eval|both, dataset_version_id?}`，仅为指定子集重新入队 jobs。

**关键点：**
- `what=infer`：新建 infer job（新 output_task_id），不触发 eval
- `what=eval`：基于当前 cell 的 `current_prediction_id` 新建 eval job
- `what=both`：新建 infer → 依赖链新 eval
- 新 job 完成后，走和 Task 9 同样的 cell 切换 + revision 记录（change_type: `rerun_infer_done` / `rerun_eval_done`）
- `dataset_version_id` 若指定，写入 cell 并用于本次 infer

### P1-Task 4: BatchRevision 历史回放

**Files:** `backend/app/routers/batches.py`, `backend/tests/test_batch_revisions.py`

**目标：**
- `GET /api/v1/batches/{id}/revisions` 返回 revision 列表
- `GET /api/v1/batches/{id}/report?rev=N` 基于该 revision 的 `snapshot_json` 还原战报（不读当前 cell，直接用 snapshot 里的 prediction/evaluation 引用查）

### P1-Task 5: 全局 Token 鉴权

**Files:** `backend/app/auth.py`, `backend/app/main.py`, `backend/tests/test_auth.py`

**目标：**
- Settings 里 `auth_token` 若非空，则所有 `/api/v1/*` 除 `/health` 都要求 `Authorization: Bearer {token}`
- 中间件实现，错误返回 401

### P1-Task 6: P1 E2E 验证

**Files:** `backend/docs/p1_e2e.md`

演示场景：
1. 创建 batch → 跑完（调用 P0 已有能力）
2. 上传 task_34 的新数据版本
3. `POST /batches/1/rerun {task_ids:[task_34_id], what:both, dataset_version_id: new_id}`
4. 观察新 prediction/evaluation 产生，cell 指针切换
5. `GET /batches/1/report` 看到新 accuracy；`?rev=2` 看到旧 accuracy
6. 启用 token，未带 header 请求收到 401

---

## P2：体验增强

### P2-Task 1: Job 日志流式接口

`GET /api/v1/jobs/{id}/log?follow=true` 以 SSE 或 chunked 返回 `log_path` 文件的持续增量，方便前端实时看推理进度。

### P2-Task 2: 每 Model 并发池

Worker 调度时，对 `status=running AND model_id=X` 计数，不超过 `Model.concurrency_limit`（新增字段，区别于"单次推理内并发"）。避免同一推理服务被压垮。

### P2-Task 3: Job 取消

`POST /api/v1/jobs/{id}/cancel` → `docker kill eval-{job_id}-{phase}` + 状态置 `cancelled`。

---

## Self-Review

按 writing-plans 的三项自检：

**1. Spec 覆盖：**

| 场景 | 实现 Task |
|------|-----------|
| 场景 1a：批量推理+评测 | P0-Task 7（Batch mode=all） |
| 场景 1b：仅批量推理 | P0-Task 7（mode=infer） |
| 场景 1c：仅批量评测 | P1-Task 3（rerun what=eval 覆盖现有 batch） |
| 场景 2a：局部重推+评 | P1-Task 3（rerun what=both） |
| 场景 2b：仅重评 | P1-Task 3（rerun what=eval） |
| 场景 2c：数据更新后重跑 | P1-Task 1 + P1-Task 2 + P1-Task 3 |
| 场景 3：模型与 Judge 可配置 | P0-Task 4 + P0-Task 5 |
| 场景 4：版本管理 | P0-Task 7（初始 revision）+ P1-Task 4（历史回放） |
| Token 鉴权 | P1-Task 5 |

所有场景均有对应 Task。

**2. Placeholder 扫描：**

已排查，P0 所有步骤有完整代码；P1/P2 是 Task 级目标描述，不包含 Step，进入实施前需细化。P0-Task 10 的 `scan.py` 明确标注"实施时需对齐 `eval_judge.py` 实际产出格式"，这是已知不确定点，不是 placeholder。

**3. Type 一致性：**

检查主要命名：
- `output_task_id`（Prediction 字段 + docker_runner 参数 + worker 使用）一致
- `model_config_key`（Model 字段 + docker_runner 参数）一致
- `suite_name`（Task 字段 + docker_runner 参数 + scan 参数）一致
- `current_prediction_id` / `current_evaluation_id`（BatchCell 字段 + report 路由使用）一致
- `build_infer_cmd` / `build_eval_cmd` / `write_env_file` 函数名在 worker.py 与 docker_runner.py 间一致
- `record_revision` 在 batch_service.py 与 worker.py 间一致

全部对齐。

---

## 交付物

执行完 P0 后可独立运行：
- 一个 FastAPI 后端服务
- 能注册模型/打分 LLM
- 能创建批次触发 docker 推理+评测
- 能查进度、看战报
- **已完全替代 `multi_deploy_benchmark_v3.sh` 的批量调度能力**

执行完 P1 后：
- 能局部重跑、上传新数据、回放历史
- **解决场景 2 和 4 的混乱**

P2 为锦上添花，不阻塞生产使用。
