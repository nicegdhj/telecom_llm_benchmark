# Score Platform 部署手册

## 1. 概述

本项目由三个 Docker 服务组成：

| 服务 | 镜像 | Dockerfile | 说明 |
|------|------|-----------|------|
| score-frontend | score-frontend:latest | deploy_docker/frontend/Dockerfile | React + nginx 前端 |
| score-backend  | score-backend:latest  | deploy_docker/backend/Dockerfile  | FastAPI 后端 + 任务调度 |
| benchmark-eval | benchmark-eval:latest | deploy_docker/ais_bench/Dockerfile | ais_bench 评测容器，由后端动态启动 |

**环境与代码分离**是本方案的核心设计：

| 内容 | 载体 | 更新方式 |
|------|------|---------|
| Python 运行时、pip 依赖、ais_bench 框架 | Docker 镜像 | 依赖变更时重新构建 |
| `eval_entry.py`、`scripts/` 业务脚本 | 宿主机 `workspace/code/` 目录（`-v` 挂载） | 直接在服务器上编辑，无需重建镜像 |
| `data/`（评测数据）、`outputs/`（结果） | 宿主机挂载目录 | 随时替换 |

---

## 2. 本机开发（本地启动）

一键构建所有镜像并启动全部服务：

```bash
bash scripts/deploy_scripts/start-local.sh        # 前台模式
bash scripts/deploy_scripts/start-local.sh -d     # 后台模式
```

脚本会自动完成：
1. 创建 `workspace/`、`backend/backend_data/` 等必要目录
2. 将 `eval_entry.py`、`scripts/`、`ais_bench/` 等软链到 `workspace/code/`
3. 构建 `benchmark-eval:latest` 镜像（已存在则跳过）
4. 宿主机 `npm run build` 构建前端 dist
5. `docker compose up --build` 启动 score-frontend + score-backend

启动后访问（整个应用挂载于 `/chuilei/eval/` 前缀，裸 `/` 会 301 跳转过去）：
- 前端：`http://localhost/chuilei/eval/`
- 后端 API：经前端 nginx 反代为 `/chuilei/eval/api/v1/...`（后端自身 `/api/v1`，前缀由 nginx 剥离）

停止服务：
```bash
docker compose -f deploy_docker/docker-compose.yml down
```

---

## 3. 私域网络部署

私域网络无公网连接，需在有网的机器上构建并导出镜像，再传输到服务器。

> **★架构前提**：华为 910C 为 `aarch64`(ARM64)。镜像 `docker save` 后**不能跨架构 load**，
> 因此**必须在 ARM64 机器上打包**（Apple Silicon Mac 即 arm64，与 910C 匹配，可直接打）。
> 切勿在 Intel/x86 机器上打包，否则 910C 导入后无法启动。

> **平台只是 HTTP 客户端，不吃 NPU**。被测模型、打分模型是独立的推理服务（如 vLLM-ascend），
> 由别处单独拉起并暴露 `IP:PORT`；910C 网络能访问到即可。其 IP/端口/密钥**不写 .env**，
> 部署后在 Web 界面「评测模型」「打分模型」中录入，由后端按需动态注入算子容器。

### 3.1 场景一：全量部署（前端 + 后端 + ais_bench）

在有网的 ARM64 机器（如开发 Mac）上执行一键打包：

```bash
bash scripts/deploy_scripts/prod_all.sh
```

脚本自动完成：
1. 宿主机 `npm run build` 构建最新前端 dist（含 `/chuilei/eval/` 前缀）
2. 构建三个镜像：`benchmark-eval`、`score-backend`、`score-frontend`
3. 导出为单一离线包 `score-platform-images.tar.gz`
4. 自带 `code/` 业务脚本（`eval_entry.py`/`eval_judge.py`/`scripts/`/`ais_bench/`）——
   后端起算子容器时 `-v` 挂载它们，缺失会导致评测一启动就失败
5. 生成生产 `docker-compose.prod.yml`（后端端口收口，仅经 nginx 暴露）、
   `.env.example`、一键铺底脚本 `init_workspace.sh`
6. 打包为 `outputs/score_platform_<timestamp>.tar.gz`

**在私域服务器上部署：**

```bash
# 1. 传输 + 解压
scp outputs/score_platform_<timestamp>.tar.gz user@server:/opt/
cd /opt && tar -xzf score_platform_<timestamp>.tar.gz && cd score_platform

# 2. 导入三个镜像
docker load < score-platform-images.tar.gz

# 3. 配置
cp .env.example .env
vi .env   # 填写 WORKSPACE_DIR、BACKEND_DATA_DIR、管理员密码

# 4. 一键建目录 + 铺 code（读取 .env）
bash init_workspace.sh

# 5. 启动服务
docker compose -f docker-compose.prod.yml --env-file .env up -d
```

访问（整个应用挂载于 `/chuilei/eval/` 前缀，裸 `/` 会 301 跳转过去）：
- 前端：`http://<服务器IP>/chuilei/eval/`
- 后端：经 nginx 反代，无需也不建议直接对外暴露 8080；如需调试，
  在 `docker-compose.prod.yml` 中临时取消 `score-backend` 的 `ports` 注释

> **注意**：
> - `benchmark-eval` 由后端通过 `docker run` 动态启动，无需在 compose 声明，但镜像必须已 load。
> - `WORKSPACE_DIR` 宿主机与容器内必须同路径，否则算子容器 `-v` 挂载失败。
> - 全部平台状态在 `BACKEND_DATA_DIR/eval_backend.db`，备份只需备份它。

### 3.2 场景二：仅部署 ais_bench 评测容器（无前后端）

适用于只需要裸跑评测任务、不需要 Web 界面的场景。

```bash
bash scripts/deploy_scripts/package_deploy.sh
```

脚本自动完成：
1. 构建 `benchmark-eval:latest` 镜像
2. 导出为 `benchmark-eval.tar.gz`
3. 打包业务脚本（`eval_entry.py`、`eval_judge.py`、`scripts/`）、数据集、启动脚本
4. 打包为 `outputs/eval_workspace_<timestamp>.tar.gz`

**在私域服务器上部署：**

```bash
# 1. 传输并解压
scp outputs/eval_workspace_<timestamp>.tar.gz user@server:/opt/
cd /opt && tar -xzf eval_workspace_<timestamp>.tar.gz
cd eval_workspace

# 2. 导入镜像
docker load < benchmark-eval.tar.gz

# 3. 配置
vi .env  # 填写 API 密钥、模型 IP/端口

# 4. 启动评测
bash run_mixed_benchmark.sh --workspace $(pwd)
```

---

## 4. 执行评测（ais_bench 容器内）

### 4.1 通过 Web 平台触发（推荐）

通过 Score Platform 前端页面提交评测任务，后端自动调度 `benchmark-eval` 容器执行。

### 4.2 直接调用 `docker run`（调试用）

```bash
docker run --rm \
    -e PYTHONUNBUFFERED=1 \
    --env-file /opt/eval_workspace/.env \
    -v /opt/eval_workspace/data:/app/data \
    -v /opt/eval_workspace/outputs:/app/outputs \
    -v /opt/eval_workspace/code/eval_entry.py:/app/eval_entry.py \
    -v /opt/eval_workspace/code/scripts:/app/scripts \
    benchmark-eval:latest \
    python eval_entry.py \
        --task-id pipeline_round_1 \
        --tasks 34 36 \
        --generic-datasets telequad_gen_0_shot mmlu_redux_gen_5_shot_str \
        --model-config local_qwen
```

> 直接 `docker run` 为前台模式，SSH 断开后进程会终止。后台运行请使用 `run_mixed_benchmark.sh`。

---

## 5. 在服务器上修改代码（无需重建镜像）

这是本方案的核心优势，业务脚本通过 `-v` 挂载，修改后立即生效。

**修改推理/评测逻辑：**

```bash
vi /opt/eval_workspace/code/eval_entry.py
# 或从本地 scp 覆盖：
scp eval_entry.py user@server:/opt/eval_workspace/code/eval_entry.py
```

**修改 ais_bench 框架内部逻辑：**

```bash
# 将 ais_bench 源码复制到服务器
scp -r ais_bench/ user@server:/opt/eval_workspace/code/ais_bench/

# 在 docker run 中追加挂载
-v /opt/eval_workspace/code/ais_bench:/app/ais_bench
```

**何时需要重建镜像：**
- 新增或升级 pip 依赖（修改 `requirements/` 文件后重新打包）

---

## 6. 查看结果

评测完成后，在 workspace 的 `outputs/<task-id>/` 下生成：

1. **`report.md`**：综合战报，便于人工浏览
2. **`report.json`**：结构化报告，适合自动解析
3. **`details/`**：单条推理结果与评分明细

重连后查看进度：

```bash
tail -f /opt/eval_workspace/logs/mixed_eval_*.log
docker ps   # 确认容器仍在运行
```

---

## 7. 脚本索引

| 脚本 | 用途 |
|------|------|
| `scripts/deploy_scripts/start-local.sh` | 本机开发一键启动 |
| `scripts/deploy_scripts/prod_all.sh` | 全量打包（前端+后端+ais_bench）用于私域部署 |
| `scripts/deploy_scripts/package_deploy.sh` | 仅打包 ais_bench 评测容器 |
| `run_mixed_benchmark.sh` | 私域服务器上启动推理+评测流程 |
| `run_eval_container.sh` | 启动常驻 ais_bench 容器（手动调试） |
