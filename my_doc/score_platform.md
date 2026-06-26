e# Score Platform — 评测管理平台 系统说明文档

> 版本：v1.0 | 日期：2026-04-22

---

## 目录

1. [系统概述](#1-系统概述)
2. [整体架构](#2-整体架构)
3. [前端功能说明](#3-前端功能说明)
4. [后端功能说明](#4-后端功能说明)
5. [数据模型](#5-数据模型)
6. [API 接口清单](#6-api-接口清单)
7. [私域网络部署指南](#7-私域网络部署指南)
8. [配置参数参考](#8-配置参数参考)
9. [常见问题排查](#9-常见问题排查)

---

## 1. 系统概述

**Score Platform** 是一套轻量级的大模型评测管理平台，将原本依赖 bash 脚本手工驱动的评测流程，封装成可编排、可增量更新、可历史追溯的 Web 服务。

### 核心价值

| 痛点（现状） | 平台解决方案 |
|---|---|
| 多模型 × 多任务需要手工排队执行 | Batch 批次一次性提交，自动调度 |
| 某个任务失败要从头重跑整批 | 局部重跑（Rerun）精确到 model × task 维度 |
| 无法回看历史某次的评测结果 | BatchRevision 版本历史，可查任意时点快照 |
| 数据集更新后旧结果难以对比 | DatasetVersion 多版本管理，历史 Prediction 保留 |
| 评测结果散落文件系统难以汇总 | 战报矩阵 + 图表可视化，一键查看 |

### 平台边界

```
┌─────────────────────────────────────────┐
│           Score Platform（本文范围）     │
│                                         │
│  score-front（React Web UI）            │
│          ↕ HTTP / REST                  │
│  score-backend（FastAPI + Worker）      │
│          ↕ docker run                   │
└────────────────┬────────────────────────┘
                 │ 调用（不修改内部逻辑）
┌────────────────┴────────────────────────┐
│   ais_bench（独立评测计算容器）          │
│   eval_entry.py / eval_judge.py         │
│   ais_bench 框架（完全不改动）          │
└─────────────────────────────────────────┘
```

平台只做**编排与结果聚合**，ais_bench 的计算逻辑完全不变。

---

## 2. 整体架构

### 2.1 部署拓扑

```
                    用户浏览器
                        │ HTTP:80
                        ▼
              ┌─────────────────┐
              │  score-front    │  Nginx（静态文件 + 反向代理）
              │  React SPA      │
              └────────┬────────┘
                       │ /api/v1/ 代理到 score-backend:8080
                       ▼
              ┌─────────────────┐
              │  score-backend  │  FastAPI + asyncio Worker
              │  SQLite DB      │
              │  Job 调度器     │
              └────────┬────────┘
                       │ docker run（通过宿主机 docker socket）
                       ▼
              ┌─────────────────┐
              │  ais_bench 容器 │  benchmark-eval:latest
              │  eval_entry.py  │  每个 Job 独立启动一个容器
              │  eval_judge.py  │
              └─────────────────┘
                       │ 读写
                       ▼
              ┌─────────────────┐
              │  宿主机文件系统  │  /opt/eval_workspace/
              │  data/  outputs/│
              └─────────────────┘
```

### 2.2 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 18 + React Router 6 + TanStack Query + Tailwind CSS + shadcn/ui 风格组件 + Recharts |
| 后端 | Python 3.10+、FastAPI、SQLAlchemy 2.x（ORM）、Pydantic v2、SQLite |
| Worker | asyncio 协程，每秒轮询 Job 表，subprocess 启动 docker 容器 |
| 打包 | 前端 Vite；后端 uvicorn |
| 容器化 | Docker + Docker Compose；前端 Nginx 多阶段构建 |
| 计算镜像 | benchmark-eval:latest（ais_bench 独立镜像） |

### 2.3 Worker 执行机制

```
FastAPI 主进程
├── HTTP 路由（CRUD + 查询）
└── Worker 协程（asyncio.create_task，随进程启动）
     ├── 每秒 poll: SELECT jobs WHERE status='pending'
     ├── 检查全局并发配额（default_job_concurrency=4）
     ├── 拼装 docker run 命令（含临时 env 文件）
     ├── subprocess.Popen → 异步 wait
     ├── infer 完成 → 登记 Prediction → 更新 BatchCell → 追加 BatchRevision
     └── eval 完成  → 登记 Evaluation → 更新 BatchCell → 追加 BatchRevision
```

---

## 3. 前端功能说明

### 3.1 页面导航结构

```
/               仪表盘（Dashboard）
/models         推理模型管理
/judges         打分模型管理
/tasks          任务列表
/batches        批次列表
/batches/:id    批次详情（战报 / 图表 / 历史 / 重跑）
/jobs           作业监控
/settings       系统设置
```

### 3.2 各页面功能详述

#### 仪表盘（Dashboard）

- 展示系统全局统计：模型数量、批次数量、进行中作业数
- 最近批次一览，快速跳转至详情

#### 推理模型管理（/models）

- 注册内网推理服务（填写 Host / Port / ModelName / 并发数）
- 编辑 / 删除已注册模型
- `model_config_key` 对应 ais_bench 配置文件名（如 `local_qwen`）

#### 打分模型管理（/judges）

- 注册用于 LLM-as-Judge 评测的打分模型
- 支持配置鉴权信息（API Key 引用）和额外环境变量

#### 任务列表（/tasks）

- 展示所有预定义评测任务（从 ais_bench 配置扫描）
- 查看任务类型（custom / generic）、数据集路径
- 上传新数据集版本（multipart 表单）
- 查看历史数据集版本列表

#### 批次列表（/batches）

- 创建新批次：选择模型集合 × 任务集合、评测模式（infer / eval / all）
- 批次卡片展示：名称、模式、创建时间、当前状态摘要

#### 批次详情（/batches/:id）

**Tab 1 — 战报矩阵**

以"模型 × 任务"二维矩阵展示评测结果：
- 每个单元格：准确率 + 运行状态（Badge 颜色标记）
- 支持切换历史 Revision 查看任意时点快照

**Tab 2 — 图表分析**

三种图表视角：
- **AccuracyBarChart**：多模型 × 多任务准确率柱状图对比
- **DurationBarChart**：多模型 × 多任务耗时柱状图对比
- **ModelTaskRadarChart**：单模型在多任务上的雷达图（覆盖全貌）

**Tab 3 — 历史版本**

- 每次 BatchCell 变更自动追加一条 Revision
- 列表展示变更类型（change_type）、变更摘要（change_summary）、时间
- 选择任意 Revision 可在战报矩阵中回放历史状态

**Tab 4 — 局部重跑**

- 勾选需要重跑的 model × task 组合
- 提交后仅对选中单元格重新发起 Job，不影响其他结果

#### 作业监控（/jobs）

- 列表展示所有 Job：类型（infer/eval）、状态、关联批次/模型/任务
- 点击日志：以轮询（每 60 秒刷新）方式加载实时日志，不勾选则不加载
- 支持取消运行中的 Job

### 3.3 前端组件体系

```
src/
├── App.jsx                  路由定义
├── features/                业务功能模块（按页面划分）
│   ├── dashboard/
│   ├── models/
│   ├── judges/
│   ├── tasks/
│   ├── batches/
│   │   └── components/      AccuracyBarChart / DurationBarChart / ModelTaskRadarChart
│   └── jobs/
├── components/
│   ├── layout/Layout.jsx    侧边栏 + 主内容区
│   └── ui/                  通用 UI 组件
│       ├── Card.jsx
│       ├── StatusBadge.jsx  状态徽章（pending/running/success/failed）
│       └── Modal.jsx
├── hooks/
│   └── useInterval.js       轮询 Hook（日志加载使用）
├── lib/
│   └── api.js               封装所有后端 API 调用 + transformReportToMatrix
└── store/
    └── authStore.js         Bearer Token 全局状态
```

---

## 4. 后端功能说明

### 4.1 服务结构

```
backend/app/
├── main.py          FastAPI 应用入口，注册路由和 Worker 生命周期
├── config.py        配置（环境变量，前缀 EVAL_BACKEND_）
├── db.py            SQLAlchemy 引擎初始化
├── deps.py          FastAPI 依赖注入（DB Session 等）
├── models.py        ORM 数据模型（10 张表）
├── schemas.py       Pydantic 请求/响应 Schema
├── routers/
│   ├── models.py    /api/v1/models
│   ├── judges.py    /api/v1/judges
│   ├── tasks.py     /api/v1/tasks
│   ├── batches.py   /api/v1/batches
│   ├── jobs.py      /api/v1/jobs
│   ├── predictions.py
│   └── evaluations.py
└── services/
    ├── worker.py       Job 调度 Worker（asyncio 协程）
    ├── batch_service.py 批次创建/重跑/战报逻辑
    ├── docker_runner.py docker run 命令拼装和执行
    ├── scan.py         扫描 ais_bench 配置目录，同步 Task 列表
    └── seed.py         数据库初始化种子数据
```

### 4.2 鉴权

所有 API 路由均受 Bearer Token 保护（除 `/api/v1/health`、`/docs`）：

```
Authorization: Bearer <EVAL_BACKEND_AUTH_TOKEN>
```

若 `EVAL_BACKEND_AUTH_TOKEN` 未配置，则跳过鉴权（开发模式）。

### 4.3 Batch 创建流程

```
POST /api/v1/batches
        │
        ├── 验证 models / tasks 列表
        ├── 创建 Batch 记录
        ├── 为每个 (model × task) 创建 BatchCell
        ├── 追加 BatchRevision（创建快照）
        └── 为每个 cell 创建 Job（infer / eval / all 模式）
              └── Worker 异步拾取执行
```

### 4.4 Docker 命令拼装

**推理 Job：**

```bash
docker run --rm \
    --memory=128g --memory-swap=128g --shm-size=16g \
    --env-file /opt/eval_backend_data/envs/{job_id}.env \
    -v {workspace_dir}/data:/app/data \
    -v {workspace_dir}/outputs:/app/outputs \
    -v {code_dir}/eval_entry.py:/app/eval_entry.py \
    -v {code_dir}/eval_judge.py:/app/eval_judge.py \
    -v {code_dir}/scripts:/app/scripts \
    --name eval-{job_id}-infer \
    benchmark-eval:latest \
    python eval_entry.py \
        --task-id {output_task_id} \
        --model-config {model.model_config_key} \
        --tasks {custom_num}            # custom 类型
        --generic-datasets {suite_name} # generic 类型
```

**评测 Job：**

```bash
... 同上挂载 ...
python eval_judge.py \
    --infer-task {output_task_id} \
    --eval-version {eval_version} \
    --eval-tasks {suite_name}
```

---

## 5. 数据模型

### 5.1 ER 关系图（逻辑）

```
Model ──────────────┐
                    ├── BatchCell (batch_id, model_id, task_id) ← Batch
Task ───────────────┤       │ current_prediction_id
  │                 │       │ current_evaluation_id
  └── DatasetVersion│
                    │
Prediction (model_id, task_id, dataset_version_id, job_id)
Evaluation (prediction_id, judge_id, job_id)

Job (type, status, batch_id, model_id, task_id, ...)

BatchRevision (batch_id, rev_num, snapshot_json)
```

### 5.2 核心表说明

| 表名 | 说明 | 不变式 |
|---|---|---|
| `models` | 推理服务注册信息 | - |
| `judges` | 打分 LLM 注册信息 | - |
| `tasks` | 评测任务（从 ais_bench 配置扫描同步） | key 全局唯一 |
| `dataset_versions` | 任务数据集版本（支持多版本） | (task_id, tag) 唯一 |
| `predictions` | 推理结果记录（不可变） | status=success 后不再修改 |
| `evaluations` | 评测结果记录（不可变） | status=success 后不再修改 |
| `batches` | 批次元数据 | - |
| `batch_cells` | 批次当前指针（可变） | (batch_id, model_id, task_id) 唯一 |
| `batch_revisions` | 批次历史快照（只增不删） | 每次 cell 变更必须在同一事务追加 |
| `jobs` | 执行记录（infer / eval） | 通过 produces_* 关联到 Prediction/Evaluation |

---

## 6. API 接口清单

### 6.1 系统

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/health` | 健康检查（免鉴权） |

### 6.2 模型管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/models` | 注册推理服务 |
| GET | `/api/v1/models` | 列表 |
| GET | `/api/v1/models/{id}` | 详情 |
| PUT | `/api/v1/models/{id}` | 更新 |
| DELETE | `/api/v1/models/{id}` | 删除 |

### 6.3 打分模型管理

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/judges` | 注册打分 LLM |
| GET | `/api/v1/judges` | 列表 |
| GET | `/api/v1/judges/{id}` | 详情 |
| PUT | `/api/v1/judges/{id}` | 更新 |
| DELETE | `/api/v1/judges/{id}` | 删除 |

### 6.4 任务与数据集

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/tasks` | 任务列表 |
| GET | `/api/v1/tasks/{id}` | 任务详情 |
| GET | `/api/v1/tasks/{id}/datasets` | 数据集版本列表 |
| POST | `/api/v1/tasks/{id}/datasets` | 上传新数据集版本（multipart） |

### 6.5 批次

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/api/v1/batches` | 创建批次（触发 Job 调度） |
| GET | `/api/v1/batches` | 批次列表 |
| GET | `/api/v1/batches/{id}` | 批次详情 |
| GET | `/api/v1/batches/{id}/report` | 战报（当前指针） |
| GET | `/api/v1/batches/{id}/report?rev=N` | 战报（历史第 N 版） |
| POST | `/api/v1/batches/{id}/rerun` | 局部重跑 |
| GET | `/api/v1/batches/{id}/revisions` | 历史版本列表 |

### 6.6 执行监控

| 方法 | 路径 | 说明 |
|---|---|---|
| GET | `/api/v1/jobs` | Job 列表 |
| GET | `/api/v1/jobs/{id}` | Job 详情 |
| GET | `/api/v1/jobs/{id}/log` | Job 日志（实时文件读取） |
| POST | `/api/v1/jobs/{id}/cancel` | 取消 Job（SIGTERM） |
| GET | `/api/v1/predictions/{id}` | 推理结果详情 |
| GET | `/api/v1/evaluations/{id}` | 评测结果详情 |

> **Swagger UI** 可访问 `http://<host>:8080/docs` 查看完整接口文档（含请求/响应 Schema）。

---

## 7. 私域网络部署指南

### 7.1 前提条件

| 组件 | 最低要求 |
|---|---|
| 宿主机 OS | Linux（推荐 Ubuntu 22.04 / CentOS 8+） |
| Docker | >= 24.0 |
| Docker Compose | >= 2.20（插件式 `docker compose`） |
| 内存 | >= 32 GB（ais_bench 容器限制 128g，实际按需） |
| 磁盘 | >= 100 GB（模型输出 + 数据集） |
| 网络 | 内网访问 inference 服务（配置 host/port） |

### 7.2 首次部署步骤

#### Step 1：克隆代码到部署机器

```bash
git clone <your-private-git-repo> /opt/score-platform
cd /opt/score-platform
```

#### Step 2：准备 ais_bench 计算镜像

如果私域环境**无法访问公网**，在有网络的机器构建后导出：

```bash
# 有网络的机器（一次性操作）
docker build -t benchmark-eval:latest .
docker save benchmark-eval:latest | gzip > benchmark-eval.tar.gz

# 传输到部署机器
scp benchmark-eval.tar.gz deploy-host:/opt/

# 部署机器导入
docker load < /opt/benchmark-eval.tar.gz
```

#### Step 3：配置环境变量

复制并编辑 `.env` 文件：

```bash
cp .env.example .env
```

编辑 `.env`，至少填写：

```bash
# 宿主机 Workspace 路径（必须和容器内一致）
WORKSPACE_DIR=/opt/eval_workspace

# 后端持久化数据目录（SQLite DB、Job 日志、临时 env 文件）
BACKEND_DATA_DIR=/opt/eval_backend_data

# （可选）API 鉴权 Token
EVAL_BACKEND_AUTH_TOKEN=your-secret-token
```

#### Step 4：初始化工作目录

```bash
chmod +x start-local.sh
./start-local.sh --build -d
```

`start-local.sh` 会自动完成：
1. 创建 `WORKSPACE_DIR/{data,outputs,code}` 目录
2. 创建 `BACKEND_DATA_DIR/{envs,logs}` 目录
3. 将 `eval_entry.py`、`eval_judge.py`、`scripts/` 复制到 `workspace/code/`
4. 构建 `score-front` 和 `score-backend` 镜像
5. 启动容器（`-d` 后台运行）

#### Step 5：验证部署

```bash
# 检查容器状态
docker compose ps

# 健康检查
curl http://localhost:8080/api/v1/health

# 访问 Web 界面
open http://localhost:80
```

### 7.3 纯离线环境（全部镜像预先导入）

如果部署机器完全离线，需要提前准备：

```bash
# 1. 导出三个镜像
docker save benchmark-eval:latest node:20-alpine nginx:alpine python:3.10-slim | gzip > all-images.tar.gz

# 2. 在部署机器导入
docker load < all-images.tar.gz

# 3. 离线构建 score-front / score-backend（需要提前缓存 npm / pip 包）
#    或在有网络的机器构建后导出
docker build -t score-front:latest ./frontend
docker build -t score-backend:latest -f backend/Dockerfile .
docker save score-front:latest score-backend:latest | gzip > platform-images.tar.gz
```

修改 `docker-compose.yml`，将 `build` 改为 `image` 直接引用：

```yaml
services:
  score-front:
    image: score-front:latest   # 替换 build 配置
    ...
  score-backend:
    image: score-backend:latest
    ...
```

### 7.4 反向代理配置（Nginx 暴露到内网）

如需通过内网域名（如 `http://score.internal`）访问，在宿主机 Nginx 添加：

```nginx
server {
    listen 80;
    server_name score.internal;

    location / {
        proxy_pass http://127.0.0.1:80;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### 7.5 数据持久化说明

| 路径（容器内） | 映射（宿主机） | 内容 |
|---|---|---|
| `${WORKSPACE_DIR}` | 与宿主机相同路径 | 数据集、推理/评测产物 |
| `/opt/eval_backend_data` | `${BACKEND_DATA_DIR}` | SQLite 数据库、Job 日志、临时 env 文件 |
| `/var/run/docker.sock` | `/var/run/docker.sock` | Docker 通信 socket |

> **重要**：`WORKSPACE_DIR` 在宿主机和容器内**必须保持相同的绝对路径**，因为后端构造的 `docker run -v` 命令中的路径，是由宿主机 Docker Daemon 解析的。

### 7.6 升级流程

```bash
# 拉取新代码
git pull

# 重新构建并重启（数据目录不受影响）
docker compose up --build -d

# 查看日志确认启动正常
docker compose logs -f score-backend
```

---

## 8. 配置参数参考

### 8.1 后端环境变量（前缀 `EVAL_BACKEND_`）

| 变量名 | 默认值 | 说明 |
|---|---|---|
| `EVAL_BACKEND_WORKSPACE_DIR` | `/opt/eval_workspace` | ais_bench 工作目录（数据集 + 输出） |
| `EVAL_BACKEND_BACKEND_DATA_DIR` | `/opt/eval_backend_data` | 后端数据目录（DB、日志、env 文件） |
| `EVAL_BACKEND_CODE_DIR` | `/opt/eval_workspace/code` | eval_entry.py 等文件所在目录 |
| `EVAL_BACKEND_DOCKER_IMAGE_TAG` | `benchmark-eval:latest` | ais_bench 计算镜像标签 |
| `EVAL_BACKEND_WORKER_POLL_INTERVAL_SEC` | `1.0` | Worker 轮询间隔（秒） |
| `EVAL_BACKEND_DEFAULT_JOB_CONCURRENCY` | `4` | 最大并行 Job 数 |
| `EVAL_BACKEND_AUTH_TOKEN` | `null`（不鉴权） | Bearer Token，不配置则跳过鉴权 |

### 8.2 docker-compose 环境变量

| 变量名 | 说明 |
|---|---|
| `WORKSPACE_DIR` | 宿主机 Workspace 绝对路径 |
| `BACKEND_DATA_DIR` | 宿主机后端数据目录绝对路径 |

在项目根目录 `.env` 文件中配置，`docker compose` 自动读取。

### 8.3 前端 API 地址配置

前端通过 Nginx 反向代理将 `/api/v1/` 转发到 `score-backend:8080`，开发时 `vite.config.js` 中配置：

```js
proxy: {
  '/api': 'http://localhost:8080'
}
```

生产环境（容器内）由 `nginx.conf` 处理，无需额外配置。

---

## 9. 常见问题排查

### Q1：后端启动后无法连接 Docker

**现象**：Job 一直处于 pending 状态，日志显示 `docker: command not found` 或 socket 权限错误

**排查**：
```bash
# 检查 docker socket 挂载
docker exec score-backend docker info

# 若权限不足，确保宿主机 docker socket 可被容器访问
ls -la /var/run/docker.sock
# 正常应为 srw-rw---- 或 srw-rw-rw-
```

### Q2：ais_bench 容器拉取失败

**现象**：Job 日志显示 `Unable to find image 'benchmark-eval:latest'`

**解决**：在宿主机确认镜像存在，容器内通过 socket 访问宿主机 Docker，镜像是宿主机镜像仓库中的。

```bash
# 宿主机验证
docker image inspect benchmark-eval:latest
```

### Q3：路径不一致导致挂载失败

**现象**：docker run 报错 `invalid mount config`

**根因**：`WORKSPACE_DIR` 在宿主机和容器内路径不一致

**解决**：确保 docker-compose.yml 中 `volumes` 挂载使用相同路径（不做路径重映射）：

```yaml
volumes:
  - ${WORKSPACE_DIR}:${WORKSPACE_DIR}  # 宿主机路径 == 容器内路径
```

### Q4：前端无法访问后端 API

**现象**：浏览器控制台报 `401 Unauthorized`

**解决**：前端 `authStore` 中配置 Bearer Token，与 `EVAL_BACKEND_AUTH_TOKEN` 保持一致。若开发调试，可暂不配置 `EVAL_BACKEND_AUTH_TOKEN`。

### Q5：SQLite 数据丢失

**现象**：重启容器后数据消失

**根因**：`BACKEND_DATA_DIR` 未挂载到宿主机

**解决**：确认 docker-compose.yml 中 `score-backend` 配置了正确的 volumes：

```yaml
volumes:
  - ${BACKEND_DATA_DIR}:/opt/eval_backend_data
```

### Q6：查看实时日志

```bash
# 后端服务日志
docker compose logs -f score-backend

# 某个 Job 的执行日志（通过 API）
curl -H "Authorization: Bearer <token>" \
     http://localhost:8080/api/v1/jobs/<job_id>/log

# 或直接查看宿主机日志文件
cat ${BACKEND_DATA_DIR}/logs/<job_id>.log
```

---

## 10. 已知限制与待优化（技术债）

### 10.1 数据集版本管理仅支持 custom 任务（单文件），generic 任务（目录）不支持 — 待统一

**问题现状**（截至 2026-06）：

平台的「数据集版本管理」（`dataset_versions` 表 + Web 上传 + `versions/<task_key>/<tag>/data.jsonl` 落盘 + 运行时软链）**目前只对 custom 任务生效**：

| 任务类型 | 数据形态 | 版本管理 | 运行时换数据的机制 |
|---------|---------|---------|------------------|
| **custom**（`task_N_suite`） | 单个 jsonl 文件 `data/custom_task/task_N.jsonl` | ✅ 支持 | `worker.py` 把固定读取路径**软链**到所选版本文件（单点替换） |
| **generic**（ceval/mmlu_redux/BBH/gpqa…） | 整个目录 `data/<dataset>/`（多子目录/多 split） | ❌ **不支持** | 无；直接读 ais_bench suite config 里写死的目录 path |

**根因**（为何当前不支持，而非简单遗漏）：

1. **数据形态不匹配**：版本模型按「单文件」设计——`dataset_versions.data_path` 指向一个文件、上传接口只收一个 `.jsonl`。generic 是整目录（如 mmlu_redux 有 57 个学科子目录、ceval 有 dev/val/test 多个 csv），「单文件=版本」套不上目录。
2. **替换机制不通用**：custom 靠 `worker.py` 软链**一个固定单点文件**实现换版本（`if run_task_type == "custom"` 分支）；generic 的读取路径写死在 ais_bench 框架 config（如 `path='data/mmlu_redux'`），worker 没有干净的劫持点，且要保证目录内部结构一致。

**当前的认知陷阱（务必注意）**：

- generic 任务在「任务与数据」上传版本、或手动往 `dataset_versions` 插记录，平台**会显示该版本、`Prediction` 也会记 `dataset_version_id`**，但 `worker` 实际跑的仍是 `data/<dataset>/` 内置数据——**该版本是“假”的、不会被使用**。这是数据管理混乱的来源之一。
- 现状下的正确操作：**custom 走版本机制（`versions/` + 脚本/上传）；generic 换数据请直接替换 `data/<dataset>/` 目录**，并自行在宿主机备份旧目录。

**优化方向（后续迭代）**：

统一为**「目录化版本管理」**，单文件作为目录的特例：

1. 版本存储统一为 `versions/<task_key>/<tag>/`**目录**（custom 仍放 `data.jsonl`，generic 放完整数据子树）；`dataset_versions.data_path` 语义从「文件」放宽为「目录或文件」。
2. `worker` 对 generic 也支持版本：对**目录**做软链/绑定挂载替换（或动态改写该 suite config 的 `path` 指向版本目录），与 custom 的单点软链统一为一套「按所选版本解析实际读取路径」的逻辑。
3. 上传接口支持目录（zip/tar 打包上传后解包）；下载接口已支持目录打包，可对称。
4. 对 generic 选了「无版本/内置」时回退到 config 原始 path，保证基准可比性不被破坏。

> 落地前请保持现状操作约定，避免给 generic 任务挂版本造成“数据看着换了、实际没换”的误判。

---

*文档由 Score Platform 开发团队整理，如有更新请同步修改本文档。*
