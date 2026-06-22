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

## 5. 第三步：在私域机器上部署（六步）

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

# 5. 放数据集（init_workspace 只建空 data/，不含数据集）
set -a; . ./.env; set +a
cp -r /你的数据目录/. "$WORKSPACE_DIR/data/"                       # 把现成的完整数据集复制进来
ln -sf "$WORKSPACE_DIR/data" "$(dirname "$WORKSPACE_DIR")/data"   # generic 任务读 dirname/data，软链到同一份
ls "$WORKSPACE_DIR/data"                                          # 应能看到 ceval/ custom_task/ 等

# 6. 启动
docker-compose -f docker-compose.prod.yml --env-file .env up -d
```

> 数据集放置细节（为何分 custom/generic 两个来源、软链原理）见 **§7.1**。数据放好后无需重启，评测时即时挂载。

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
# ★放在版本无关的数据根下（见 §6.1），不要写进 score_platform_<日期> 版本目录
WORKSPACE_DIR=/opt/eval_platform/score_data/eval_workspace
BACKEND_DATA_DIR=/opt/eval_platform/score_data/eval_backend_data

# 首次启动初始化的管理员账号（建库后再改请到平台内修改）
EVAL_BACKEND_ADMIN_USERNAME=admin
EVAL_BACKEND_ADMIN_PASSWORD=change_me_please
```

| 变量 | 说明 |
|------|------|
| `FRONT_PORT` | 前端对外的**宿主机端口**，默认 8087。访问即 `http://<IP>:<FRONT_PORT>/chuilei/eval/`。改端口只改这里，无需动 compose。 |
| `WORKSPACE_DIR` | 数据/结果/业务脚本根目录。**宿主机与容器内必须同路径**；放版本无关的数据根，建议 `/opt/eval_platform/score_data/eval_workspace`（见 §6.1）。 |
| `BACKEND_DATA_DIR` | 平台数据库、运行日志、动态 env。容器内固定挂到 `/opt/eval_backend_data`；宿主机侧建议 `/opt/eval_platform/score_data/eval_backend_data`。 |
| `EVAL_BACKEND_ADMIN_USERNAME/PASSWORD` | **仅首次启动建库时写入**。之后改密码请登录平台操作，改 .env 无效。 |

> **被测/打分模型不在这里配**。它们的 IP、端口、API Key、并发，**部署后在 Web 界面录入**（见 §9）。`.env` 里若残留 `MAAS_/LOCAL_/SCORE_` 字段，那是裸跑 ais_bench 用的，对平台无效。

### 6.1 数据与版本解耦（强烈推荐的目录约定）

**铁律：数据目录和 `.env` 放在「与版本无关的固定路径」，版本目录只放可丢弃的发布物。**
否则把 `WORKSPACE_DIR=.../score_platform_0617/eval_workspace` 这样写进版本目录里，会导致：旧版目录永远删不掉（活数据在里面）、每次升级都要手改 .env、版本与数据耦死。

推荐布局：**一个父目录下，数据根（`score_data`）与各版本发布目录（`score_platform_<日期>`）平级**，数据独立于版本：

```
/opt/eval_platform/                          ← 平台总目录
├── score_data/                              ← ★数据根（版本无关，永不随发布走）
│   ├── .env                                 ★权威配置，只此一份
│   ├── eval_workspace/                      WORKSPACE_DIR（data/ outputs/ code/）
│   ├── eval_backend_data/                   BACKEND_DATA_DIR（eval_backend.db ...）
│   └── data  ─→ eval_workspace/data         generic 软链（init_workspace 自动建）
├── score_platform_0617/                     ← 旧版发布目录（镜像包+compose，留作回滚）
├── score_platform_0622/                     ← 新版发布目录（解压即用，可随时删旧版）
└── score_platform_current ─→ score_platform_0622   ← 可选：软链指向当前线上版本
```

`.env` 里数据路径指向数据根，**与发布目录无关**：

```bash
WORKSPACE_DIR=/opt/eval_platform/score_data/eval_workspace
BACKEND_DATA_DIR=/opt/eval_platform/score_data/eval_backend_data
```

这样每次升级都是**一条命令**（见 §11.2）：`bash $BASE/platform_update.sh --pkg <新包>`——它自动解压新版目录、软链共享数据根 `.env`、备份库、停旧起新、健康检查、切换 `current`。数据始终在数据根，发布目录随便删留。

> 已经把数据放进了版本目录（如 0617 内）？一次性迁出即可，见 §11.5。

---

## 7. 目录结构与数据挂载

`init_workspace.sh` 执行后形成：

```
/opt/eval_platform/score_data/eval_workspace/    ← WORKSPACE_DIR（容器内外同路径）
├── data/                         评测数据集（★init 后为空，需自行放入，见 §7.1）
├── outputs/                      评测结果（体量大，注意磁盘）
└── code/                         业务脚本（-v 挂载，改完即生效，无需重建镜像）
    ├── eval_entry.py  eval_judge.py  setup.py
    ├── scripts/
    └── ais_bench/                框架源码（算子容器挂载它，必须完整）

/opt/eval_platform/score_data/eval_backend_data/ ← BACKEND_DATA_DIR
├── eval_backend.db               ★SQLite，全部平台状态，备份就备它
├── backups/                      platform_update.sh 升级前自动备份的历史库
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

### 7.1 数据集放置（重要，`init_workspace.sh` 只建空 data/，不含数据集）

**数据集既不在部署包里，也没烤进镜像**（`benchmark-eval` 镜像声明 `VOLUME ["/app/data"]`，数据靠 `-v` 外挂）。评测时后端起算子容器，按**任务类型**把宿主机数据挂到容器 `/app/data`：

| 任务类型 | 宿主机数据来源（`WORKSPACE_DIR=/opt/eval_workspace` 时） |
|---------|--------------------------------------------------------|
| **custom**（task_1/34/36…） | `WORKSPACE_DIR/data` → `/opt/eval_workspace/data` |
| **generic**（ceval/mmlu/gpqa…） | `dirname(WORKSPACE_DIR)/data` → **`/opt/data`** |

> 「任务与数据」页的版本数来自**数据库**（init 已 seed），所以**列表与 init 版本一定能看到**；磁盘上没有真实数据**不影响 UI**，但**评测会因 `/app/data` 为空而失败**，下载也拉不到文件。

**推荐：一份真实数据 + 一个软链，三处全通（custom / generic / 后端下载）。**
`init_workspace.sh` 已自动建好 `dirname(WORKSPACE_DIR)/data → WORKSPACE_DIR/data` 软链，你只需把数据集放进 `WORKSPACE_DIR/data`：

```bash
set -a; . ./.env; set +a

# 把数据集拷/解压到 WORKSPACE_DIR/data，最终形如：
#   $WORKSPACE_DIR/data/ceval/...  mmlu_redux/...  custom_task/task_1.jsonl ...
cp -r /你的数据源/* "$WORKSPACE_DIR/data/"        # 或 tar -xzf datasets.tar.gz -C "$WORKSPACE_DIR/data"

# 确认软链存在（init_workspace.sh 已建；缺了就补）
PARENT_DATA="$(dirname "$WORKSPACE_DIR")/data"
[ -e "$PARENT_DATA" ] || ln -s "$WORKSPACE_DIR/data" "$PARENT_DATA"

ls -l "$PARENT_DATA"           # 应指向 $WORKSPACE_DIR/data
ls "$WORKSPACE_DIR/data"       # 应能看到 ceval/ custom_task/ 等真实目录
```

- `docker run -v` 在**宿主机**解析软链，算子容器照样读到真实数据；不用改 compose、不用重启（挂载在每个 job 起算子容器时即时发生）。
- 不想用软链也可放两份真实目录：generic 放 `/opt/data`、custom 放 `/opt/eval_workspace/data`，效果一样但占双份空间。
- 数据集如何传到私域机：在打包机 `tar -czf datasets.tar.gz -C <项目根> data` 后 `scp` 过去，解压到 `WORKSPACE_DIR/data` 即可（数据集体量大，故不随平台包走）。

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
cp /opt/eval_platform/score_data/eval_backend_data/eval_backend.db \
   /opt/backup/eval_backend_$(date +%F).db
```

**升级平台（系统已上线、要保留老数据）**：见 **§11 迭代更新**，用 `platform_update.sh --pkg <新包>` 一键完成（自动备份数据库 + 停旧起新 + 健康检查 + 切 current）。

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
- 即便如此，`platform_update.sh` 升级前仍会**自动备份 `eval_backend.db`** 并做完整性校验，最坏情况可一键还原。

### 11.2 一键升级（唯一更新脚本 `platform_update.sh`）

前提：已按 §6.1 建立数据/版本解耦布局（数据根 `/opt/eval_platform/score_data`，权威 `.env` 在其中）。
`platform_update.sh` 常驻平台目录 `BASE`（首次从任意新包里取一份放到 `BASE` 即可，之后它会自更新）。
**日常更新就一条命令**——把新包放到 `BASE`，指给脚本：

```bash
# 【打包机·ARM64·联网】出新包并传到平台目录
bash scripts/deploy_scripts/prod_all.sh
scp outputs/score_platform_<新时间戳>.tar.gz user@<910C_IP>:/opt/eval_platform/

# 【私域机·910C】一条命令完成升级
bash /opt/eval_platform/platform_update.sh \
     --pkg /opt/eval_platform/score_platform_<新时间戳>.tar.gz
```

它自动完成 7 步：**前置检查 → 解压新版目录 + 软链共享 `.env` → 备份数据库 → 导入新镜像 → 停旧 + 同步 code + 起新 → 健康检查 → 切换 `current` 软链**。
内置安全检查：docker/磁盘/架构、数据根与 `.env` 存在性、**是否有评测在跑**（提示）、备份完整性校验、健康检查失败则**不切 current 并给回滚指引**。数据全程在数据根、不动；旧版本目录保留作回滚、确认无误后可删。

常用选项：

```bash
--pkg <tar.gz>          必填：新版离线包
--name score_platform_0630   版本目录名（默认取包名去掉 .tar.gz）
--base <目录>           平台目录（默认脚本所在目录）
-y                      跳过确认（自动化）
-h                      查看用法
```

> ⚠️ 升级前最好确认**没有正在跑的评测**（脚本会检测并提示）。停容器会中断后端 Worker，正在执行的算子容器会变孤儿、对应任务需重跑——但**已落库的历史结果不受影响**。

### 11.3 手动升级（等价步骤，便于理解 / 应急）

```bash
BASE=/opt/eval_platform
REL=$BASE/score_platform_0630
set -a; . "$BASE/score_data/.env"; set +a     # 取数据路径

# 1. 解压新包 + 软链共享 .env
mkdir -p "$REL" && tar -xzf "$BASE/score_platform_<新时间戳>.tar.gz" -C "$REL" --strip-components=1
ln -sf "$BASE/score_data/.env" "$REL/.env"

# 2. 备份数据库（关键！）
mkdir -p "$BACKEND_DATA_DIR/backups"
cp -p "$BACKEND_DATA_DIR/eval_backend.db" "$BACKEND_DATA_DIR/backups/eval_backend_$(date +%F_%H%M%S).db"

# 3. 导入新镜像 → 停旧 → 同步 code → 起新
cd "$REL"
docker load < score-platform-images.tar.gz
docker-compose -f docker-compose.prod.yml --env-file .env down
bash init_workspace.sh
docker-compose -f docker-compose.prod.yml --env-file .env up -d

# 4. 验证 + 切换 current
curl -fsS http://localhost:${FRONT_PORT:-8087}/chuilei/eval/api/v1/health   # 期望 {"status":"ok"}
ln -sfn "$REL" "$BASE/score_platform_current"
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

### 11.5 一次性：把数据迁出版本目录（老部署纠正）

若历史上把数据放进了版本目录（如 `.env` 指向 `.../score_platform_0617/eval_workspace`），趁一次升级把它迁到版本无关的数据根，以后即可走 §11.2 的固定流程：

```bash
# 1. 停旧系统（释放数据库/文件占用）
cd <旧版目录>/score_platform_0617
docker-compose -f docker-compose.prod.yml --env-file .env down

# 2. 数据搬到版本无关的数据根
mkdir -p /opt/eval_platform/score_data
mv <旧版目录>/score_platform_0617/eval_workspace    /opt/eval_platform/score_data/eval_workspace
mv <旧版目录>/score_platform_0617/eval_backend_data /opt/eval_platform/score_data/eval_backend_data

# 3. 在数据根放一份权威 .env（把数据路径改成指向数据根）
cp <旧版目录>/score_platform_0617/.env /opt/eval_platform/score_data/.env
sed -i 's#.*WORKSPACE_DIR=.*#WORKSPACE_DIR=/opt/eval_platform/score_data/eval_workspace#; \
        s#.*BACKEND_DATA_DIR=.*#BACKEND_DATA_DIR=/opt/eval_platform/score_data/eval_backend_data#' \
        /opt/eval_platform/score_data/.env

# 4. 取出更新脚本并一键升级（数据根与 .env 已就绪）
tmp=$(mktemp -d) && tar -xzf /opt/eval_platform/score_platform_<新时间戳>.tar.gz -C "$tmp" --strip-components=1
cp "$tmp/platform_update.sh" /opt/eval_platform/platform_update.sh && rm -rf "$tmp"
bash /opt/eval_platform/platform_update.sh --pkg /opt/eval_platform/score_platform_<新时间戳>.tar.gz -y
```

> 上述一次性迁移也可直接用脚本 `scripts/deploy_scripts/migrate_0617_to_decoupled.sh`（改好顶部变量后一把跑完）。

迁完后旧目录只剩部署包文件，删留随意；之后所有升级都只需 §11.2 三步。

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

**已上线系统的升级（保留老数据，数据/版本解耦见 §6.1、§11）：一条命令**

```bash
# 前提：数据与 .env 已在数据根 /opt/eval_platform/score_data，platform_update.sh 常驻 BASE（见 §6.1、§11.2）
scp outputs/score_platform_<新时间戳>.tar.gz user@<910C>:/opt/eval_platform/
bash /opt/eval_platform/platform_update.sh --pkg /opt/eval_platform/score_platform_<新时间戳>.tar.gz
# 自动：解压→软链共享 .env→备份库→导入新镜像→停旧起新→健康检查→切换 current
```
