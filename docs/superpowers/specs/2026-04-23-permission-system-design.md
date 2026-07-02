# 权限管理系统设计（轻量版）

> **创建日期**：2026-04-23
> **目标读者**：后续实施 agent / 维护者
> **设计原则**：KISS、与现有架构最小冲突、不引入新基础设施

---

## 1. 目标与范围

### 1.1 目标

为现有的"评测后端系统"补一个**最小可用**的多用户与权限层，使得：

1. 系统支持多用户登录（用户名 + 密码），不再仅靠单一共享 token
2. 角色分两类业务权限（`operator` 写、`viewer` 只读），外加 `admin` 用于用户管理
3. 关键资源（`Batch`、`Job`、`BatchRevision`）能记录"是谁创建/修改的"，并在前端按要求显示

### 1.2 非目标（YAGNI）

- 不做按资源粒度的细分权限（不做"模型管理可读、测评管理可写"这种交叉矩阵）
- 不做完整 audit log 表（用现有 `BatchRevision` 表挂用户即可）
- 不做找回密码、邮件验证、OAuth、SSO
- 不做"踢人下线"看在线用户等高级功能（删 session 即可粗暴下线）
- 不引入 Alembic：用一次性手写迁移脚本

---

## 2. 整体架构

```
┌─────────────────┐      POST /auth/login         ┌─────────────────┐
│  React 前端     │  ──────────────────────────►  │  FastAPI 后端   │
│  (LoginPage)    │  ◄──── { session_token } ──── │  (auth router)  │
└────────┬────────┘                               └────────┬────────┘
         │ Bearer <session_token>                          │
         │ (复用现有 api.js)                                │
         ▼                                                 ▼
┌─────────────────┐                              ┌──────────────────┐
│  authStore      │                              │  current_user    │
│  + currentUser  │                              │  依赖注入解析    │
└─────────────────┘                              └────────┬─────────┘
                                                          ▼
                                                 ┌──────────────────┐
                                                 │  路由 + RBAC     │
                                                 │  写操作填 actor  │
                                                 └──────────────────┘
```

**关键设计点**：

| # | 决策 | 理由 |
|---|------|------|
| 1 | 三种角色：`admin`（含全部 operator 能力 + 用户管理）/ `operator` / `viewer` | 用户明确选 A：全局二元业务权限，admin 独立 |
| 2 | 随机字符串 session（非 JWT），存 `user_sessions` 表 | 用户明确选"不用 token"，最小成本满足 HTTP 无状态需求 |
| 3 | 鉴权移到 FastAPI 依赖注入层，删除现有 `_auth_middleware` | 中间件无法按路由细分权限；依赖注入与 OpenAPI 集成更好 |
| 4 | `EVAL_BACKEND_AUTH_TOKEN`（旧单 token）保留作为虚拟系统 admin bypass | 不破坏现有 curl/CI 调试脚本 |
| 5 | admin 通过环境变量初始化（仅首次），DB 为准 | 部署友好，密码可在前端轮换 |
| 6 | 用户软删除（`is_active=False`），外键 `ON DELETE SET NULL` 兜底 | 历史 `Batch.created_by` 不会成野指针 |
| 7 | 操作记录：`Batch.created_by_user_id`、`Batch.last_modified_by_user_id`、`BatchRevision.actor_user_id`、`Job.created_by_user_id`，其他表不加 | 命中"测评管理 + 执行记录"原始需求；其他表加字段成本极低，留待未来 |
| 8 | 前端显示策略：BatchDetail 头部显示创建人/最后修改人，JobsPage 列表加"提交人"列；其余位置不显示 | 严格按用户最终选定的"测评管理 C / 执行记录 A / 其他 B" |

---

## 3. 数据模型变更

### 3.1 新增表

**`users`**

| 字段 | 类型 | 约束/默认 | 说明 |
|------|------|----------|------|
| id | Integer | PK | |
| username | String | UNIQUE, NOT NULL | 登录名 |
| password_hash | String | NOT NULL | bcrypt 哈希 |
| role | String | NOT NULL | `admin` / `operator` / `viewer` |
| display_name | String | NULLable | 中文姓名等，前端优先显示 |
| is_active | Boolean | DEFAULT TRUE, NOT NULL | 软删除/停用 |
| last_login_at | DateTime | NULLable | 最后一次成功登录时间 |
| created_at | DateTime | DEFAULT now | |
| updated_at | DateTime | DEFAULT/onupdate now | |

**`user_sessions`**

| 字段 | 类型 | 约束 | 说明 |
|------|------|------|------|
| id | Integer | PK | |
| token | String | UNIQUE, NOT NULL, INDEX | `secrets.token_urlsafe(32)` |
| user_id | Integer | FK→users.id, NOT NULL | |
| created_at | DateTime | DEFAULT now | |
| last_used_at | DateTime | DEFAULT now | 每次请求更新（轻量 UPDATE） |
| expires_at | DateTime | NOT NULL | created_at + TTL（默认 7 天） |

> 没有 `revoked` 字段。登出/踢人 = 删除该行。
> 过期清理：worker_loop 每小时扫一次 `DELETE FROM user_sessions WHERE expires_at < now()`。

### 3.2 现有表新增字段

| 表 | 新增字段 | 类型 | 说明 |
|----|---------|------|------|
| `batches` | `created_by_user_id` | Integer FK→users.id, NULLable, ON DELETE SET NULL | 创建人 |
| `batches` | `last_modified_by_user_id` | Integer FK→users.id, NULLable, ON DELETE SET NULL | 最后修改人（rerun / cell 变更时更新） |
| `batch_revisions` | `actor_user_id` | Integer FK→users.id, NULLable, ON DELETE SET NULL | 该次 revision 的触发人；**前端暂不展示**，留待后用 |
| `jobs` | `created_by_user_id` | Integer FK→users.id, NULLable, ON DELETE SET NULL | 提交人 |

**用户显示统一规则**（前后端各处复用）：

```
if user_id is None:
    显示 "系统"  # 来自 EVAL_BACKEND_AUTH_TOKEN bypass，或 ON DELETE SET NULL 后未识别
elif user is None:
    显示 "已删除用户"  # 理论上不会出现（软删除），兜底
elif not user.is_active:
    显示 f"{display_name or username}（已停用）"
else:
    显示 user.display_name or user.username
```

### 3.3 配置项变更（`backend/app/config.py`）

新增字段：

```python
# 兜底/调试用，沿用旧逻辑
auth_token: str | None = None

# 新增
admin_username: str = "admin"
admin_password: str | None = None        # 仅首次启动时初始化使用
session_ttl_hours: int = 168             # 7 天
session_cleanup_interval_sec: int = 3600 # 每小时清理一次
```

`.env.example` 增加：

```bash
EVAL_BACKEND_ADMIN_USERNAME=admin
EVAL_BACKEND_ADMIN_PASSWORD=请改为强密码
EVAL_BACKEND_SESSION_TTL_HOURS=168
```

### 3.4 迁移策略

不引入 Alembic。新增 `backend/scripts/migrate_v2_add_auth.py`：

**`schema_version` 表**（极简，单行）：

| 字段 | 类型 | 约束 |
|------|------|------|
| version | Integer | PK |

**迁移流程（启动时由 `init_db()` 调用，幂等）**：

1. `create_all()`：SQLAlchemy 按当前 ORM 定义创建所有缺失的表（全新库直接到位；老库会创建 `users` / `user_sessions` 但不会改 `batches` 等已存在表）
2. 读 `schema_version`：表不存在 → 建表并写入版本 1
3. 若当前版本 < 2，对**已存在的旧表**做 `ALTER`（用 `PRAGMA table_info(...)` 检查列是否存在，已存在则跳过该列；SQLite 不支持 IF NOT EXISTS for ADD COLUMN）：
   - `ALTER TABLE batches ADD COLUMN created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL`
   - `ALTER TABLE batches ADD COLUMN last_modified_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL`
   - `ALTER TABLE batch_revisions ADD COLUMN actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL`
   - `ALTER TABLE jobs ADD COLUMN created_by_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL`
4. 写入 `schema_version = 2`

> 全新部署的库：`create_all` 已经按 ORM 定义把新字段加上，第 3 步的列检查会全部跳过——天然幂等。
> 旧库升级：`create_all` 创建新表 + 第 3 步补列，覆盖旧库。

### 3.5 admin 初始化逻辑

`init_db()` 收尾：

```python
if settings.admin_password and not session.query(User).filter_by(username=settings.admin_username).first():
    session.add(User(
        username=settings.admin_username,
        password_hash=bcrypt_hash(settings.admin_password),
        role="admin",
        display_name="超级管理员",
        is_active=True,
    ))
    session.commit()
```

**幂等**：已存在该 admin 用户则不动（DB 为准），不会被环境变量覆盖。

---

## 4. API 设计

### 4.1 新增认证路由（`backend/app/routers/auth.py`）

| 方法 | 路径 | 权限 | 请求/响应 |
|------|------|------|----------|
| POST | `/api/v1/auth/login` | 公开 | req: `{username, password}` → res: `{session_token, expires_at, user}` |
| POST | `/api/v1/auth/logout` | 已登录 | 删除当前 session |
| GET | `/api/v1/auth/me` | 已登录 | 返回当前用户 |
| POST | `/api/v1/auth/change-password` | 已登录 | req: `{old_password, new_password}` |

`/login` 失败时统一返回 401 `"用户名或密码错误"` 或 403 `"账号已停用"`。

### 4.2 新增用户管理路由（`backend/app/routers/users.py`）

| 方法 | 路径 | 权限 | 说明 |
|------|------|------|------|
| GET | `/api/v1/users` | admin | 列出所有用户（含已停用） |
| POST | `/api/v1/users` | admin | 创建：`{username, password, role, display_name?}` |
| PUT | `/api/v1/users/{id}` | admin | 改 role / display_name / is_active |
| POST | `/api/v1/users/{id}/reset-password` | admin | `{new_password}` |
| DELETE | `/api/v1/users/{id}` | admin | 等价于 `PUT {is_active: false}` + 删除该用户所有 session |

**业务约束**（后端强制校验）：

1. 不允许删除/停用系统中**最后一个 active 的 admin**
2. 不允许把唯一的 active admin 改成非 admin
3. admin 不能停用/删除自己

### 4.3 鉴权依赖（`backend/app/deps.py`）

替换/扩展原 `verify_token`：

```python
def current_user(authorization: str = Header(None), db: Session = Depends(db_session)) -> User:
    """
    解析 Bearer <token>:
      1. 若 token == settings.auth_token，返回虚拟 system admin（不入 DB）
      2. 否则查 user_sessions：未找到 / 已过期 → 401；返回关联 user
      3. 用户 is_active=False → 403
      4. 命中后更新 last_used_at（轻量）
    """

def require_role(*allowed_roles: str):
    def dep(user: User = Depends(current_user)) -> User:
        if user.role not in allowed_roles:
            raise HTTPException(403, "Forbidden")
        return user
    return dep
```

### 4.4 RBAC 应用矩阵

| 路由组 | GET | POST/PUT/DELETE/rerun/cancel |
|--------|-----|-----------------------------|
| `/auth/login` | 公开 | 公开 |
| `/auth/me`、`/auth/logout`、`/auth/change-password` | `current_user` | `current_user` |
| `/users/**` | `require_role("admin")` | `require_role("admin")` |
| `/models`、`/judges`、`/tasks`、`/batches`、`/jobs`、`/predictions`、`/evaluations` | `require_role("viewer", "operator", "admin")` | `require_role("operator", "admin")` |
| `/health`、`/docs`、`/openapi.json`、`/redoc` | 公开 | 公开 |

实施时**整体替换** `Depends(verify_token)` 为合适的 `Depends(...)`，是局部依赖项升级，不重写业务逻辑。

### 4.5 中间件清理

删除 `main.py` 中的 `_auth_middleware`（现已无用），鉴权统一到依赖注入层。

### 4.6 写操作的 actor 自动填充

| 端点 | 行为 |
|------|------|
| `POST /batches` | `Batch.created_by_user_id = current_user.id`、`Batch.last_modified_by_user_id = current_user.id`；派生的 Job 也填 `created_by_user_id`；首条 BatchRevision 填 `actor_user_id` |
| `POST /batches/{id}/rerun` | 更新 `Batch.last_modified_by_user_id`；新 Job 填 `created_by_user_id`；新 BatchRevision 填 `actor_user_id` |
| 任何触发 `BatchCell` 变更并 append `BatchRevision` 的代码路径 | 同步填两处：`BatchRevision.actor_user_id` 与 `Batch.last_modified_by_user_id` |

> service 层接口签名小调整：相关函数（如 `batch_service.create_batch(...)`、`batch_service.rerun_batch(...)`）多接一个 `actor: User` 参数。这是必要的局部重构。

### 4.7 Schema 输出扩展

`BatchOut`、`JobOut` 新增字段：

```python
class UserBrief(BaseModel):
    id: int
    username: str
    display_name: str | None
    role: str
    is_active: bool

class BatchOut(...):
    created_by: UserBrief | None
    last_modified_by: UserBrief | None

class JobOut(...):
    created_by: UserBrief | None
```

后端通过 `joinedload(Batch.created_by, Batch.last_modified_by)` 等避免 N+1。

---

## 5. 前端改动

### 5.1 store（`src/store/authStore.js`）

扩展现有 store，新增 `user` 字段与 `setSession/clearSession/isAdmin/canWrite` 方法（详见设计章节 4.1）。`token` 字段名不变，`api.js` 的 Bearer 头逻辑无需改动。

### 5.2 `api.js` 扩展

新增 `auth` 与 `users` 两个分组（约 30 行），并在 `request()` 的 401 分支自动 `clearSession + 跳 /login`。

### 5.3 路由保护（`App.jsx`）

```
/login                            → LoginPage（公开）
/*                                → RequireAuth + Layout
  ├─ /                            → Dashboard
  ├─ /batches、/jobs、/models 等  → 已登录即可见
  └─ /users                       → RequireAdmin + UsersPage
```

新增组件：

- `RequireAuth`：未登录跳 `/login`
- `RequireAdmin`：非 admin 跳 `/`（兜底，主要靠 Sidebar 隐藏入口）

### 5.4 新增页面

**`src/pages/LoginPage.jsx`**
居中卡片：用户名 + 密码 + 登录按钮。失败显示后端错误。

**`src/features/users/UsersPage.jsx`**（admin only）
- 表格列：`username`、`display_name`、`role`、`状态（启用/停用）`、`最后登录`、`创建时间`、`操作`
- 顶栏按钮：`新增用户`
- 行操作：`编辑`（role / display_name / 启停用）、`重置密码`、`删除`
- 弹窗：`UserFormModal`、`ResetPasswordModal`
- 前端镜像后端约束：不能停用/删除最后一个 admin、不能停用自己 → 按钮置灰 + tooltip

### 5.5 SettingsPage 改造

- 删除"填写 API Token"卡片（登录即获得 token）
- 新增"修改密码"卡片：所有已登录用户可见

### 5.6 Sidebar 改造

- 顶部"当前用户"卡片：`<display_name 或 username>` · `<角色徽章>` · `[退出]`
- 菜单项 `用户管理`：仅 admin 可见
- 退出：调 `api.auth.logout` → `clearSession` → 跳 `/login`

### 5.7 操作人显示（按需求严格执行）

| 位置 | 是否显示 | 内容 |
|------|---------|------|
| `BatchesPage` 列表 | 否 | — |
| `BatchDetailPage` 头部 | **是** | `创建人：xxx · 最后修改人：xxx`（用户显示规则见 §3.2） |
| `BatchDetailPage` 时间线 | 否 | （后端字段已存，前端先不显示） |
| `JobsPage` 列表 | **是** | 新增"提交人"列 |
| `ModelsPage` / `JudgesPage` / `TasksPage` | 否 | — |

### 5.8 写操作按钮的角色门禁

viewer 角色登录后，所有写操作按钮**置灰 + tooltip 提示无权限**（不是隐藏）。
实现：用一个 `<RoleButton requiredRole="operator">` 包装组件读取 `useAuthStore`。
后端是真正的安全防线，前端只做体验层。

---

## 6. 兼容性与安全

| 项 | 处理 |
|----|------|
| 旧 `EVAL_BACKEND_AUTH_TOKEN` | 保留：作为虚拟 system admin bypass，便于调试与 CI |
| 旧前端 SettingsPage 中存的 token | 用户首次升级后会失效（非合法 session）→ 触发 401 自动跳 `/login` |
| 密码存储 | bcrypt（passlib），绝不存明文 |
| 密码强度 | 不校验（内网环境，admin 自负其责）|
| token 传输 | 复用现有 Bearer 头方案，部署在内网/HTTPS 网关后 |
| 防爆破 | 不做（内网信任模型）|
| CSRF | 不做（无 cookie，纯 Bearer 头，天然免疫）|

---

## 7. 实施顺序建议（供 writing-plans 参考）

1. 数据层：models / migration 脚本 / config / admin 初始化
2. 认证依赖：`current_user`、`require_role`，删除旧中间件
3. auth router + users router
4. 现有 router 替换 `verify_token` → `current_user` / `require_role(...)`
5. 写操作处填充 `created_by` / `actor`，扩展 schema 输出
6. 前端 store / api / 路由守卫
7. 前端 LoginPage / UsersPage / SettingsPage / Sidebar
8. 前端各处操作人显示 + 角色门禁
9. 端到端联调与测试

---

## 8. 测试要点

- 单元：bcrypt 哈希/校验、session 过期判定、迁移脚本幂等性
- 集成（pytest + httpx）：
  - login → 用 token 调 `/auth/me` → logout → 再调 `/auth/me` 应 401
  - viewer 调 POST `/batches` 应 403
  - admin 不能停用最后一个 admin / 不能停用自己
  - 旧 `EVAL_BACKEND_AUTH_TOKEN` 仍能调通业务接口
- 前端手动：登录/退出、admin 用户管理、viewer 看到置灰按钮、详情页与 JobsPage 显示操作人
