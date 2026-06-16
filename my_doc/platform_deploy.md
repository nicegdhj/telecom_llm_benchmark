# 垂类大模型评测平台 · 私域部署手册（platform_deploy.md）

> 本文档只讲**评测平台（前后端 Web）**如何部署到私域网络机器（如华为 910C）。
> 裸跑 ais_bench 的部署见 `my_doc/deploy.md`，平台设计见 `my_doc/score_platform.md`。

---

## 1. 总体架构

平台由 **3 个 Docker 镜像** + **1 个动态算子容器**组成：

| 组件 | 镜像 | 角色 | 对外端口 |
|------|------|------|---------|
| 前端 | `score-frontend:latest` | nginx + React，整个应用挂载于 `/chuilei/eval/`，并反代 API 到后端 | **宿主机 `FRONT_PORT`（默认 8087）→ 容器 80** |
| 后端 | `score-backend:latest` | FastAPI + Worker，调度评测、存库、出报告 | 仅内网络 `expose 8080` |
| 算子 | `benchmark-eval:latest` | ais_bench 评测容器，**由后端经 docker.sock 动态 `docker run`，跑完即销毁** | 无 |

```
浏览器 ──http://IP:8087/chuilei/eval/──▶ score-front(宿主8087→容器nginx:80)
                                       │  静态资源 + 反代 /chuilei/eval/api/ → score-backend:8080
                                       ▼
                                  score-backend(FastAPI+Worker)
                                       │  经 /var/run/docker.sock 动态 docker run
                                       ▼
                                  benchmark-eval(算子容器, 临时)
                                       │  HTTP 请求
                                       ▼
                            被测模型 / 打分模型服务（独立, IP:PORT）
```

**关键认知（先记住，避免踩坑）：**

1. **平台不吃 NPU**。它只是 HTTP 客户端。被测模型、打分模型是**独立的推理服务**（如 vLLM-ascend），由别处单独拉起并暴露 `IP:PORT`，910C 网络能访问到即可。
2. **模型地址不写在 .env**。被测/打分模型的 `IP/端口/密钥/并发`**部署后在 Web 界面里录入**，由后端按任务动态注入算子容器。
3. **架构必须一致**。910C 是 `aarch64`(ARM64)，镜像 `docker save` 后**不能跨架构 load**，因此**必须在 ARM64 机器上打包**（Apple Silicon Mac 即 arm64，匹配）。
4. **WORKSPACE_DIR 宿主机内外同路径**。后端经宿主机 docker.sock 起算子容器，docker daemon 解析的是宿主机路径，所以容器内外路径必须一致（生产直接用 `/opt/eval_workspace`）。
5. **全部平台状态在一个 SQLite 文件**：`BACKEND_DATA_DIR/eval_backend.db`，备份只备它。

---

## 2. 前提条件

**打包机（联网，ARM64）：**
- Docker（daemon 运行中）、Node.js + npm（构建前端 dist）
- 能联网拉取镜像基础层 / pip / npm（仅打包时需要，打包产物自包含）

**私域机器（910C / 任意 aarch64 Linux）：**
- 已安装 Docker + docker-compose（V1，`docker-compose version` 可用）
- 磁盘建议 ≥ 50 GB（镜像约 4 GB，`outputs/` 评测结果会持续增长）
- 网络可访问被测/打分模型服务的 `IP:PORT`
- 对外端口（默认 `FRONT_PORT=8087`）空闲；被占用见 §12，改 `.env` 即可换端口

---

## 3. 第一步：在联网 ARM64 机器上打包

```bash
cd <项目根目录>
bash scripts/deploy_scripts/prod_all.sh
```

脚本自动完成（已内置架构守卫，非 ARM64 会告警）：

1. `npm run build` 构建最新前端 dist（含 `/chuilei/eval/` 前缀）
2. 构建 3 个镜像：`benchmark-eval` / `score-backend` / `score-frontend`
3. `docker save` 三镜像为单一离线包 `score-platform-images.tar.gz`
4. 自带 `code/` 业务脚本（`eval_entry.py` / `eval_judge.py` / `setup.py` / `scripts/` / 完整 `ais_bench/`）—— 后端起算子容器时 `-v` 挂载它们，缺失会导致评测一启动就失败
5. 生成 `docker-compose.prod.yml`（后端端口收口）、`.env.example`、一键铺底脚本 `init_workspace.sh`
6. 打包为 `outputs/score_platform_<时间戳>.tar.gz`

**产物结构：**

```
score_platform/
├── score-platform-images.tar.gz   # 三镜像离线包（aarch64）
├── docker-compose.prod.yml        # 生产 Compose（后端 expose，不映射宿主端口）
├── .env.example                   # 环境变量模板
├── init_workspace.sh              # 一键建目录 + 铺 code
├── code/                          # 业务脚本（被挂进算子容器，必须完整）
│   ├── eval_entry.py  eval_judge.py  setup.py
│   ├── scripts/
│   └── ais_bench/                 # 评测框架源码（-v 覆盖镜像内同名目录）
└── README.txt
```

---

## 4. 第二步：传输到私域机器

```bash
scp outputs/score_platform_<时间戳>.tar.gz user@<910C_IP>:/opt/
```

> 无法 scp 的隔离环境，用移动介质拷贝该单一 tar.gz 即可，自包含、无外部依赖。

---

## 5. 第三步：在私域机器上部署（五步）

```bash
# 1. 解压
cd /opt && tar -xzf score_platform_<时间戳>.tar.gz && cd score_platform

# 2. 导入三个镜像（一次导入）
docker load < score-platform-images.tar.gz

# 3. 配置环境变量
cp .env.example .env
vi .env        # 见 §6，至少填 WORKSPACE_DIR / BACKEND_DATA_DIR / 管理员密码

# 4. 一键建目录 + 铺 code（脚本读取 .env）
bash init_workspace.sh

# 5. 启动
docker-compose -f docker-compose.prod.yml --env-file .env up -d
```

**访问**（注意带前缀，裸 `/` 会 301 跳过去）：

```
http://<910C_IP>:8087/chuilei/eval/
```

用 `.env` 里的管理员账号登录。

---

## 6. 配置详解（.env）

```bash
# 前端对外端口（宿主机），按需修改；容器内 nginx 固定 80
FRONT_PORT=8087

# Workspace / 数据目录（宿主机绝对路径，容器内外保持一致）
WORKSPACE_DIR=/opt/eval_workspace
BACKEND_DATA_DIR=/opt/eval_backend_data

# 首次启动初始化的管理员账号（建库后再改请到平台内修改）
EVAL_BACKEND_ADMIN_USERNAME=admin
EVAL_BACKEND_ADMIN_PASSWORD=change_me_please
```

| 变量 | 说明 |
|------|------|
| `FRONT_PORT` | 前端对外的**宿主机端口**，默认 8087。访问即 `http://<IP>:<FRONT_PORT>/chuilei/eval/`。改端口只改这里，无需动 compose。 |
| `WORKSPACE_DIR` | 数据/结果/业务脚本根目录。**宿主机与容器内必须同路径**，生产建议 `/opt/eval_workspace`。 |
| `BACKEND_DATA_DIR` | 平台数据库、运行日志、动态 env。容器内固定挂到 `/opt/eval_backend_data`。 |
| `EVAL_BACKEND_ADMIN_USERNAME/PASSWORD` | **仅首次启动建库时写入**。之后改密码请登录平台操作，改 .env 无效。 |

> **被测/打分模型不在这里配**。它们的 IP、端口、API Key、并发，**部署后在 Web 界面录入**（见 §9）。`.env` 里若残留 `MAAS_/LOCAL_/SCORE_` 字段，那是裸跑 ais_bench 用的，对平台无效。

---

## 7. 目录结构与数据挂载

`init_workspace.sh` 执行后形成：

```
/opt/eval_workspace/              ← WORKSPACE_DIR（容器内外同路径）
├── data/                         评测数据集
├── outputs/                      评测结果（体量大，注意磁盘）
└── code/                         业务脚本（-v 挂载，改完即生效，无需重建镜像）
    ├── eval_entry.py  eval_judge.py  setup.py
    ├── scripts/
    └── ais_bench/                框架源码（算子容器挂载它，必须完整）

/opt/eval_backend_data/           ← BACKEND_DATA_DIR
├── eval_backend.db               ★SQLite，全部平台状态，备份就备它
├── envs/                         worker 为每个 job 动态生成的 .env
└── logs/

/var/run/docker.sock              挂进后端，使其能动态起算子容器
```

三类挂载在 `docker-compose.prod.yml` 中体现为：

```yaml
volumes:
  - ${WORKSPACE_DIR}:${WORKSPACE_DIR}              # 同路径挂载
  - ${BACKEND_DATA_DIR}:/opt/eval_backend_data
  - /var/run/docker.sock:/var/run/docker.sock      # docker-in-docker 关键
```

---

## 8. 启动后验证

```bash
# 容器状态
docker-compose -f docker-compose.prod.yml ps          # score-front / score-backend 应 Up

# 日志
docker-compose -f docker-compose.prod.yml logs -f score-backend

# 入口连通性（裸路径应 301 到 /chuilei/eval/）
curl -I http://localhost:8087/                              # 期望 301
curl -I http://localhost:8087/chuilei/eval/                # 期望 200
```

浏览器打开 `http://<910C_IP>:8087/chuilei/eval/` → 登录 → 进入仪表盘即部署成功。

---

## 9. 录入模型并跑通一次评测

1. **评测模型**：录入被测模型的接入方式（MaaS / 本地 vLLM / 通用 API）、`IP/端口/模型名/并发`（必要时 API Key）。
2. **打分模型**：同理录入裁判模型。
3. **任务与数据**：确认评测任务（数据集）已就绪。
4. **测评管理**：新建批次，选模型 × 任务，提交。后端 Worker 会自动 `docker run` 算子容器执行推理 + 评测，结果落库。
5. 在**测评分析**查看结果、对比、导出。

> 跑通前请确认 910C 能访问模型服务：`curl http://<模型IP>:<端口>/v1/models` 或对应健康检查。

---

## 10. 运维

**改业务脚本（无需重建镜像）**：直接编辑 `WORKSPACE_DIR/code/` 下文件，下次评测即生效。

**备份**（核心只有一个文件）：
```bash
cp /opt/eval_backend_data/eval_backend.db /opt/backup/eval_backend_$(date +%F).db
```

**升级平台（系统已上线、要保留老数据）**：见 **§11 迭代更新**，用随包附带的 `upgrade.sh` 一键完成（自动备份数据库 + 停旧起新 + 健康检查）。

**停止 / 启动：**
```bash
docker-compose -f docker-compose.prod.yml down          # 停止（保留数据）
docker-compose -f docker-compose.prod.yml --env-file .env up -d   # 启动
```

---

## 11. 迭代更新（在线系统升级，保留老数据）

> 适用：系统**已上线运行一段时间**、积累了模型/批次/评测结果等数据，现在要更新到新版本。
> 核心原则：**业务数据全在宿主机挂载目录，不随镜像走**；升级只换镜像和 code，数据原样保留，且升级前自动备份。

### 11.1 升级为什么不会丢数据

| 数据 | 位置 | 升级时 |
|------|------|--------|
| 平台状态（用户/模型/批次/预测/评测/分析） | `BACKEND_DATA_DIR/eval_backend.db` | 宿主机文件，`down`/`up`/`docker load` 都不碰 |
| 评测结果产物 | `WORKSPACE_DIR/outputs/` | 宿主机目录，不随镜像走 |
| 数据集 / 上传版本 | `WORKSPACE_DIR/data/` | 宿主机目录，不随镜像走 |
| 业务脚本 | `WORKSPACE_DIR/code/` | `init_workspace.sh` 覆盖式同步为新版 |

- `docker-compose down` **不带 `-v`** 只删容器和网络，**绝不动 bind 挂载目录**。
- 后端新版本启动时会**自动迁移数据库 schema**（幂等的 `run_migrations` + `ALTER TABLE`），并幂等补种任务/init 版本，老数据保留、不重复。
- 即便如此，`upgrade.sh` 升级前仍会**自动备份 `eval_backend.db`** 并做完整性校验，最坏情况可一键还原。

### 11.2 一键升级（推荐）

打包机（ARM64）重新出包 → 传到私域机 → 解压到**新目录** → 沿用旧 `.env` → 跑 `upgrade.sh`：

```bash
# 【打包机·ARM64·联网】出新包
bash scripts/deploy_scripts/prod_all.sh
scp outputs/score_platform_<新时间戳>.tar.gz user@<910C_IP>:/opt/

# 【私域机·910C】解压到新目录，复用旧 .env
cd /opt && tar -xzf score_platform_<新时间戳>.tar.gz -C /opt/score_platform_new --strip-components=1 2>/dev/null \
  || { mkdir -p /opt/score_platform_new && tar -xzf score_platform_<新时间戳>.tar.gz -C /opt/score_platform_new --strip-components=1; }
cd /opt/score_platform_new
cp /opt/score_platform/.env ./.env          # 复用线上旧 .env（WORKSPACE_DIR/BACKEND_DATA_DIR 等保持不变）

# 一键升级（会先备份数据库，再停旧起新，最后健康检查）
bash upgrade.sh
```

`upgrade.sh` 自动完成 6 步：**前置检查 → 备份数据库 → 导入新镜像 → 停旧容器 → 同步 code → 起新容器 → 健康检查**。
带的安全检查：必备文件/`.env`/docker、磁盘空间、架构提示、**是否有评测算子容器正在运行**（有则提示，避免中断在跑的任务）、备份完整性校验、启动后健康检查失败给出**回滚指引**。

常用参数：

```bash
bash upgrade.sh           # 交互确认（默认）
bash upgrade.sh -y        # 跳过确认，适合自动化
bash upgrade.sh -h        # 查看说明
```

> ⚠️ 升级前最好确认**没有正在跑的评测**（`upgrade.sh` 会检测并提示）。停容器会中断后端 Worker，正在执行的算子容器会变孤儿，对应任务需重跑——但**已落库的历史结果不受影响**。

### 11.3 手动升级（等价步骤，便于理解）

```bash
cd /opt/score_platform_new            # 新版包目录，已复用旧 .env
set -a; . ./.env; set +a

# 1. 备份数据库（关键！）
cp "$BACKEND_DATA_DIR/eval_backend.db" "$BACKEND_DATA_DIR/eval_backend_$(date +%F_%H%M%S).db"

# 2. 导入新镜像（覆盖同名 :latest）
docker load < score-platform-images.tar.gz

# 3. 停旧容器（不带 -v，数据安全）
docker-compose -f docker-compose.prod.yml --env-file .env down

# 4. 同步业务脚本到 WORKSPACE_DIR/code
bash init_workspace.sh

# 5. 起新容器
docker-compose -f docker-compose.prod.yml --env-file .env up -d

# 6. 验证
curl -fsS http://localhost:${FRONT_PORT:-8087}/chuilei/eval/api/v1/health   # 期望 {"status":"ok"}
docker-compose -f docker-compose.prod.yml ps
```

### 11.4 回滚

新版本异常时（健康检查失败 / 功能回归）：

```bash
docker-compose -f docker-compose.prod.yml --env-file .env down
# 还原数据库（如新版迁移后想退回，用升级前的备份）
cp "$BACKEND_DATA_DIR/backups/eval_backend_<时间戳>.db" "$BACKEND_DATA_DIR/eval_backend.db"
# 重新导入上一版本镜像包（★建议每次升级保留上一版 tar.gz），再 up
docker load < <上一版本>/score-platform-images.tar.gz
docker-compose -f docker-compose.prod.yml --env-file .env up -d
```

> 建议：**每次升级前保留上一版的 `score-platform-images.tar.gz`**（镜像无法从运行中容器反向导出，留包是唯一可靠的镜像回滚手段）；数据库备份在 `BACKEND_DATA_DIR/backups/`，可放心还原。

---

## 12. 常见问题排查

| 现象 | 原因 | 处理 |
|------|------|------|
| `docker load` 报 `exec format error` / 启动即退出 | 镜像与机器**跨架构**（在 x86 打的包） | 必须在 ARM64 机器重新 `prod_all.sh` |
| 端口被占用 / 启动报 `address already in use` | 宿主机已有服务占用该端口 | 改 `.env` 的 `FRONT_PORT`（如 8087→别的值），重新 `up -d` |
| 访问端口后**莫名跳到另一个端口**（如访问 80 跳到 9096） | 该端口被**宿主机上别的服务**占用，score-front 因冲突没起来，命中的是旧服务 | `docker-compose ps` 确认 score-front 是否 Up；`lsof -i :<端口>` 查占用；换一个空闲 `FRONT_PORT` |
| 提交评测后 job 一直 pending / 立即失败 | 算子容器起不来 | 见下三项逐一排查 |
| 算子容器报挂载失败 / 找不到 eval_entry.py | `code/` 没铺好，或 `WORKSPACE_DIR` 内外路径不一致 | 重跑 `bash init_workspace.sh`；确认 .env 的 `WORKSPACE_DIR` 是宿主机真实绝对路径 |
| 后端日志 `permission denied /var/run/docker.sock` | 后端容器无权访问宿主 docker | 确认 socket 已挂载；宿主 `chmod 666 /var/run/docker.sock` 或将运行用户加入 docker 组 |
| 算子容器报连不上模型 | 910C 访问不到模型 `IP:PORT` | 在宿主 `curl` 验证模型服务可达；检查界面录入的 IP/端口 |
| 前端能打开但接口 401/跳登录 | 未登录或会话过期 | 用 .env 管理员账号登录；会话默认 7 天 |
| 改了 .env 管理员密码不生效 | 该项仅首次建库使用 | 登录平台内修改密码 |

---

## 13. 一页速查

```bash
# 【打包机·ARM64·联网】
bash scripts/deploy_scripts/prod_all.sh
scp outputs/score_platform_*.tar.gz user@910C:/opt/

# 【私域机·910C】
cd /opt && tar -xzf score_platform_*.tar.gz && cd score_platform
docker load < score-platform-images.tar.gz
cp .env.example .env && vi .env
bash init_workspace.sh
docker-compose -f docker-compose.prod.yml --env-file .env up -d
# 访问 http://<910C_IP>:8087/chuilei/eval/
```

**已上线系统的升级（保留老数据，见 §11）：**

```bash
# 打包机出新包并传过去后，私域机解压到新目录、复用旧 .env：
cd /opt/score_platform_new
cp /opt/score_platform/.env ./.env
bash upgrade.sh          # 自动：备份库 → 停旧 → 导入新镜像 → 同步 code → 起新 → 健康检查
```
