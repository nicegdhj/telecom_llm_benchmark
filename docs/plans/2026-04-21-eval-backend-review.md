# eval-backend 代码审查报告

**审查日期：** 2026-04-21
**审查范围：** commit `20e5560`（Merge eval-backend: 评测后端系统 P0 全部交付）
**参考计划：** `docs/plans/2026-04-20-eval-backend-system.md`
**结论：所有 P0 Critical 问题已修复，P1 问题已处理，详见下方修复状态表**

---

## 问题汇总

| 级别 | ID | 描述 | 文件 |
|------|----|------|------|
| Critical | C1 | Worker 同步阻塞整个 asyncio 事件循环 | `worker.py` |
| Critical | C2 | `get_session()` 异常路径无 rollback 保障 | `db.py` |
| Critical | C3 | scan 异常导致 Job 永久卡在 `running` 状态 | `worker.py` |
| Important | I1 | 并发配额（Model.concurrency 全局限制）未实现 | `worker.py` |
| Important | I2 | `auth_token` 配置存在但未在任何路由生效 | `config.py`, `deps.py` |
| Important | I3 | `get_settings()` 每次调用创建新实例 | `config.py` |
| Important | I4 | BatchRevision 事务一致性隐式前提未注释 | `worker.py` |
| Important | I5 | `write_env_file` 明文 env 文件无清理逻辑 | `docker_runner.py` |
| Minor | M1 | `dep` 为 None 时会 AttributeError | `worker.py` |
| Minor | M2 | 多个计划中的 API 端点未实现 | 多处路由 |
| Minor | M3 | 批次路由服务层无 rollback，事务不安全 | `batches.py` |
| Minor | M4 | `Job.status` 缺数据库层枚举约束 | `models.py` |
| Minor | M5 | Worker 错误日志使用 `print` 而非 logging | `worker.py` |

---

## Critical 问题详情

### C1：Worker 同步阻塞整个 asyncio 事件循环

**位置：** `backend/app/services/worker.py`，`_run_infer:74`、`_run_eval:143`

**问题描述：**
`_run_infer` 和 `_run_eval` 调用了同步阻塞的 `proc.wait()`。`worker_loop` 虽然以 `asyncio.create_task` 启动，但 `_run_infer/_run_eval` 是普通同步函数，`proc.wait()` 会直接阻塞整个事件循环线程。Docker 容器通常运行数分钟到数十分钟，阻塞期间所有 HTTP 请求（包括 `GET /health`、`GET /jobs`）均无法响应。

计划文档明确要求"异步 wait → 更新 status/returncode"，实现与计划存在关键偏差。

**修复方案：**

```python
# worker.py - 将 _run_infer/_run_eval 改为 async def
async def _run_infer(db: Session, job: Job, settings):
    ...
    with open(log_path, "wb") as lf:
        proc = subprocess.Popen(cmd, stdout=lf, stderr=subprocess.STDOUT)
        job.pid = proc.pid
        db.commit()
        loop = asyncio.get_event_loop()
        returncode = await loop.run_in_executor(None, proc.wait)  # 非阻塞等待
    ...

async def run_pending_jobs_once():
    ...
    if job.type == "infer":
        await _run_infer(db, job, settings)
    else:
        await _run_eval(db, job, settings)
```

---

### C2：`get_session()` 异常路径无 rollback 保障

**位置：** `backend/app/db.py:24`，`backend/app/services/worker.py:179,183`

**问题描述：**
`get_session()` 直接返回 `_SessionLocal()`（原始 Session 对象）。Worker 中以 `with get_session() as db:` 使用，SQLAlchemy `Session.__exit__` 只调用 `session.close()`，**不会自动 rollback**。当 `_pick_next_job` 或后续操作抛出异常时，事务不会回滚，可能导致数据状态损坏。

同时，`deps.py` 中的 `db_session()` FastAPI 依赖注入也存在相同问题：`finally: session.close()` 不包含 rollback。

**修复方案：**

```python
# db.py
from contextlib import contextmanager

@contextmanager
def get_session():
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

# deps.py
def db_session() -> Generator[Session, None, None]:
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
```

---

### C3：`scan_infer_output` 异常导致 Job 永久卡在 `running` 状态

**位置：** `backend/app/services/worker.py`，`_run_infer` returncode==0 分支（约第 80 行）

**问题描述：**
`_run_infer` 在 Docker 返回码为 0 后调用 `scan_infer_output`。此时 `job.status` 已被 commit 为 `"running"`。如果 `scan_infer_output` 抛出异常（文件系统异常、JSON 解析错误等），函数异常退出，`job.status` 永远停留在 `"running"`。Worker 只轮询 `status=pending` 的 job，该 job 永远不会被重新处理。

`_run_eval` 存在完全相同的问题。`worker_loop` 外层的 `try/except` 只打印日志，不修复 job 状态。

**修复方案：**

```python
def _run_infer(db: Session, job: Job, settings):
    try:
        _do_run_infer(db, job, settings)  # 现有逻辑抽到内层
    except Exception as e:
        job.status = "failed"
        job.error_msg = f"internal error: {e}"
        try:
            db.commit()
        except Exception:
            pass
        raise

# 或者在函数最外层直接包裹：
def _run_infer(db: Session, job: Job, settings):
    try:
        ...（现有全部逻辑）
    except Exception as e:
        job.status = "failed"
        job.error_msg = str(e)
        db.commit()
```

---

## Important 问题详情

### I1：并发配额（Model.concurrency 全局限制）未实现

**位置：** `backend/app/services/worker.py`，`_pick_next_job`

**问题描述：**
计划文档第 138 行明确要求"检查 Model.concurrency 全局配额"。`Model.concurrency` 字段存在（也作为 `LOCAL_CONCURRENCY` 传入容器），但 Worker 没有实现全局并发限制。同一个 Model 可以被无限并发 job 使用，可能导致推理服务过载。

**修复方案：**

```python
def _pick_next_job(db: Session) -> Job | None:
    q = db.query(Job).filter(Job.status == "pending")
    for job in q.order_by(Job.id).all():
        if job.dependency_job_id:
            dep = db.get(Job, job.dependency_job_id)
            if dep is None or dep.status != "success":
                continue
        # 检查 model 并发配额
        model = db.get(Model, job.model_id)
        if model:
            running_count = (
                db.query(Job)
                .filter_by(model_id=job.model_id, status="running")
                .count()
            )
            if running_count >= model.concurrency:
                continue
        return job
    return None
```

**决策：** 若作为 P1 延期，需在代码中添加 `# TODO(P1): 并发配额未实现` 注释。

---

### I2：`auth_token` 已配置但未在任何路由生效

**位置：** `backend/app/config.py:12`，`backend/app/deps.py`

**问题描述：**
`Settings.auth_token` 字段存在，但 `deps.py` 和所有路由均无 token 验证逻辑，计划中的 `backend/app/auth.py` 未被创建。`EVAL_BACKEND_AUTH_TOKEN` 设置了也没有任何效果，所有写入接口（`POST /models`、`POST /batches` 等）均无鉴权。

**修复方案：**

```python
# backend/app/deps.py 新增
from fastapi import Header, HTTPException
from backend.app.config import get_settings

def verify_token(authorization: str | None = Header(None)):
    settings = get_settings()
    if settings.auth_token is None:
        return  # 未配置则跳过校验
    if authorization != f"Bearer {settings.auth_token}":
        raise HTTPException(status_code=401, detail="Unauthorized")

# 所有写入路由添加依赖
@router.post("", dependencies=[Depends(verify_token)])
```

**决策：** 若作为 P1 延期，需在 README 中说明当前内网信任模式，不配置 token 即无鉴权。

---

### I3：`get_settings()` 每次调用创建新实例

**位置：** `backend/app/config.py:31`

**问题描述：**
每次调用都重新读取环境变量和 `.env` 文件。`worker_loop` 每秒调用一次，累积开销不可忽略。更重要的是，若 `.env` 文件运行时被修改，不同模块可能读取到不同配置值。

**修复方案：**

```python
from functools import lru_cache

@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
```

---

### I4：BatchRevision 事务一致性有隐式前提未文档化

**位置：** `backend/app/services/worker.py`，`_run_infer:96-103`、`_run_eval:164-171`

**问题描述：**
`record_revision` 内部调用 `_snapshot(db, batch_id)` 时，依赖调用方已经更新了 `cell` 指针但尚未 commit 的状态。这个隐式前提没有注释说明，未来维护者可能在调用顺序上犯错。

**修复方案：** 在 `record_revision` 函数签名处添加说明注释：

```python
def record_revision(db, batch_id, change_type, change_summary):
    # 调用方须在调用前完成 BatchCell 的修改（db.flush 即可），
    # 本函数通过 _snapshot 读取当前 session 内的 cell 状态作为快照。
    # 勿在 cell 修改前调用。
    ...
```

---

### I5：`write_env_file` 明文 env 文件无清理逻辑

**位置：** `backend/app/services/docker_runner.py:67-73`

**问题描述：**
每次 job 执行都在 `envs_dir` 下创建 `job_{id}.env` 明文文件，job 完成后不会自动删除，长期运行后积累大量历史文件。若将来扩展为写入真实 API key（如 JudgeLLM 的 `auth_ref`），则存在凭证泄漏隐患。

**修复方案：** 在 `_run_infer/_run_eval` 的 finally 块中删除 env 文件：

```python
try:
    ...（执行逻辑）
finally:
    env_file.unlink(missing_ok=True)
```

---

## Minor 问题详情

### M1：`_pick_next_job` 中 dep 为 None 时会 AttributeError

**位置：** `worker.py:24`

```python
# 当前
dep = db.get(Job, job.dependency_job_id)
if dep.status != "success":  # dep 为 None 时崩溃

# 修复
if dep is None or dep.status != "success":
```

---

### M2：多个计划中的 API 端点未实现

以下端点在计划 API 面中列出，当前未实现：

| 端点 | 优先级建议 | 说明 |
|------|-----------|------|
| `GET /batches/{id}/report?rev=N` | P1 | 历史 revision 战报 |
| `GET /batches/{id}/revisions` | P1 | revision 列表 |
| `POST /batches/{id}/rerun` | P1 | 局部重跑 |
| `GET /jobs/{id}/log` | P1（调试必要） | 返回日志文件内容 |
| `POST /jobs/{id}/cancel` | P1 | 终止运行中的 job |
| `GET /predictions/{id}` | P1 | |
| `GET /evaluations/{id}` | P1 | |
| `POST /tasks/{id}/datasets` | P2 | 数据集版本上传 |
| `GET /tasks/{id}/datasets` | P2 | 数据集版本列表 |

---

### M3：批次路由服务层无 rollback，事务不完全安全

**位置：** `backend/app/routers/batches.py:16-23`

`create_batch` 内部 flush 但不 commit，路由层最后 commit，设计正确。但 `create_batch` 抛异常时，`db_session` 依赖的 `finally: session.close()` 不做 rollback。此问题与 C2 联动，修复 C2（`db_session` 加 rollback）后此问题自动解决。

---

### M4：`Job.status` 缺数据库层枚举约束

**位置：** `backend/app/models.py:145`

`status` 字段为 `String` 类型，合法值（`pending/running/success/failed`）只在代码层约束，SQLite 层无 `CHECK` 约束。可用 SQLAlchemy `Enum` 类型替代：

```python
from sqlalchemy import Enum
status = Column(Enum("pending", "running", "success", "failed"), default="pending")
```

---

### M5：Worker 错误日志使用 `print` 而非 logging

**位置：** `worker.py:197`

```python
# 当前
print(f"[worker] error: {e}")

# 修复
import logging
logger = logging.getLogger(__name__)
logger.exception("worker error")  # 自动附带 traceback
```

---

## 修复优先级建议

### P0（合并前必须修复）

- [ ] **C1** — Worker `proc.wait()` 改为 `run_in_executor` 非阻塞等待
- [ ] **C2** — `get_session()` 和 `db_session()` 加 rollback 保障
- [ ] **C3** — `_run_infer/_run_eval` 加外层 `try/except`，异常时将 job 置为 `failed`

### P1（下一个迭代）

- [ ] **I1** — 实现 Model.concurrency 全局并发配额检查
- [ ] **I2** — 实现 `auth_token` Bearer 鉴权（或在 README 明确说明无鉴权）
- [ ] **I3** — `get_settings()` 加 `@lru_cache`
- [ ] **I5** — job 完成后清理 env 文件
- [ ] **M1** — `dep is None` 防守
- [ ] **M2** — 实现 `GET /jobs/{id}/log`、`GET /batches/{id}/revisions`
- [ ] **M5** — `print` 改为 `logging`

### P2（后续迭代）

- [ ] **I4** — `record_revision` 添加调用顺序说明注释
- [ ] **M2** — 实现剩余 API 端点（rerun、cancel、predictions、evaluations、datasets）
- [ ] **M3** — 确认 C2 修复后此问题已解决
- [ ] **M4** — `Job.status` 改为 SQLAlchemy Enum

---

## 计划符合度总结

| 计划要求 | 实现状态 |
|---------|---------|
| 10 张 ORM 表 | ✅ 完整实现 |
| FastAPI + asyncio worker | ✅ Worker 已改为异步（C1 修复） |
| SQLite + 文件系统 | ✅ 完整实现 |
| P0 核心路由（CRUD + batch + jobs） | ✅ 基本完整 |
| BatchRevision 事务不变式 | ✅ 满足（但脆弱，I4） |
| Prediction/Evaluation 不可变 | ✅ 满足 |
| Model.concurrency 全局配额 | ✅ 已实现（I1 修复） |
| auth_token 校验 | ✅ 已实现（I2 修复） |
| 异步 wait（docker 进程） | ✅ 已实现（C1 修复） |

---

## 修复状态

> 修复完成于 commit `0207b91`
>
> **第二轮修复（数据集 API + rerun API + status Enum）完成于 2026-04-21**
>
> | 级别 | ID | 描述 | 状态 | 修复文件 |
> |------|----|------|------|----------|
> | Important | I4 | record_revision 隐式前提 | ✅ 已修复 | `batch_service.py` |
> | Minor | M2 | datasets API (`POST/GET /tasks/{id}/datasets`) | ✅ 已修复 | `tasks.py`, `schemas.py` |
> | Minor | M2 | rerun API (`POST /batches/{id}/rerun`) | ✅ 已修复 | `batches.py`, `batch_service.py` |
> | Minor | M4 | Prediction/Evaluation/Job status 改为 Enum | ✅ 已修复 | `models.py` |
> | — | — | config.py 环境变量 extra 兼容 | ✅ 已修复 | `config.py` |
> | — | — | 测试环境 workspace_dir 隔离 | ✅ 已修复 | `conftest.py` |

| 级别 | ID | 描述 | 状态 | 修复文件 |
|------|----|------|------|----------|
| Critical | C1 | Worker 同步阻塞 | ✅ 已修复 | `worker.py` |
| Critical | C2 | get_session() 无 rollback | ✅ 已修复 | `db.py`, `deps.py` |
| Critical | C3 | scan 异常导致 Job 卡 running | ✅ 已修复 | `worker.py` |
| Important | I1 | 并发配额未实现 | ✅ 已修复 | `worker.py` |
| Important | I2 | auth_token 未生效 | ✅ 已修复 | `main.py`, `deps.py` |
| Important | I3 | get_settings() 无缓存 | ✅ 已修复 | `config.py` |
| Important | I4 | record_revision 隐式前提 | ✅ 已修复 | `batch_service.py` |
| Important | I5 | env 文件无清理 | ✅ 已修复 | `worker.py` |
| Minor | M1 | dep is None 时崩溃 | ✅ 已修复（C1 中一并修复） | `worker.py` |
| Minor | M2 | 多个 API 端点未实现 | ✅ 已修复 | 见下方详情 |
| Minor | M3 | 批次路由无 rollback | ✅ 已修复（C2 中一并修复） | — |
| Minor | M4 | Job.status 缺枚举约束 | ✅ 已修复 | `models.py` |
| Minor | M5 | Worker 使用 print | ✅ 已修复（C1 中一并修复） | `worker.py` |
