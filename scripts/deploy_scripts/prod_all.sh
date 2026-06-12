#!/usr/bin/env bash
# ==============================================================================
# prod_all.sh —— Score Platform 私域全量打包脚本
#
# 功能：
#   1. 在宿主机构建前端 dist（frontend/Dockerfile 是 COPY dist，不会自己 build）
#   2. 构建三个 Docker 镜像：
#      - benchmark-eval:latest   (ais_bench 评测计算容器)
#      - score-backend:latest    (FastAPI 后端服务)
#      - score-frontend:latest   (React + nginx 前端，挂载于 /chuilei/eval/)
#   3. 将三个镜像导出为单一离线包 score-platform-images.tar.gz
#   4. 自带 workspace 业务脚本 code/（eval_entry/eval_judge/scripts/ais_bench…）
#      —— 后端调度算子容器时通过 -v 挂载它们，缺失会导致评测一启动就失败
#   5. 生成生产 docker-compose.prod.yml + .env.example + 一键铺底脚本 init_workspace.sh
#   6. 打包为 score_platform_<timestamp>.tar.gz，放入 outputs/
#
# 用法：
#   bash scripts/deploy_scripts/prod_all.sh
#
# 前提：
#   - 已安装 Docker 且 daemon 运行；已安装 node/npm（用于构建前端 dist）
#   - ★必须在 ARM64(aarch64) 机器上打包（华为 910C 为 aarch64，跨架构 load 会失败）
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_ROOT"

TIMESTAMP="$(date +%Y%m%d_%H%M%S)"
PACKAGE_NAME="score_platform_${TIMESTAMP}"
OUTPUTS_DIR="$PROJECT_ROOT/outputs"
TMP_DIR="/tmp/${PACKAGE_NAME}"
PKG_DIR="$TMP_DIR/score_platform"
IMAGES_FILE="score-platform-images.tar.gz"

echo "======================================================"
echo "  Score Platform 私域全量打包"
echo "  输出: $OUTPUTS_DIR/${PACKAGE_NAME}.tar.gz"
echo "======================================================"

mkdir -p "$OUTPUTS_DIR"

# ── Step 1: 检查必要文件 + 架构提示 ───────────────────────────────
echo ""
echo "▶ [1/6] 检查依赖文件..."

[ -f "$PROJECT_ROOT/deploy_docker/ais_bench/Dockerfile" ] || { echo "❌ 缺少 deploy_docker/ais_bench/Dockerfile"; exit 1; }
[ -f "$PROJECT_ROOT/deploy_docker/backend/Dockerfile" ]   || { echo "❌ 缺少 deploy_docker/backend/Dockerfile"; exit 1; }
[ -f "$PROJECT_ROOT/deploy_docker/frontend/Dockerfile" ]  || { echo "❌ 缺少 deploy_docker/frontend/Dockerfile"; exit 1; }
[ -f "$PROJECT_ROOT/eval_entry.py" ]                      || { echo "❌ 缺少 eval_entry.py"; exit 1; }
[ -f "$PROJECT_ROOT/eval_judge.py" ]                      || { echo "❌ 缺少 eval_judge.py"; exit 1; }
[ -d "$PROJECT_ROOT/ais_bench" ]                          || { echo "❌ 缺少 ais_bench/ 框架源码"; exit 1; }
[ -d "$PROJECT_ROOT/scripts" ]                            || { echo "❌ 缺少 scripts/ 目录"; exit 1; }
command -v node >/dev/null 2>&1 || { echo "❌ 未找到 node，请先安装 Node.js（用于构建前端）"; exit 1; }

HOST_ARCH="$(uname -m)"
echo "  ✅ 文件检查通过（打包机架构: ${HOST_ARCH}）"
if [ "${HOST_ARCH}" != "aarch64" ] && [ "${HOST_ARCH}" != "arm64" ]; then
    echo "  ⚠️  当前不是 ARM64！华为 910C 为 aarch64，跨架构镜像无法 load。"
    echo "      请在 ARM64 机器上打包，或确认目标机器架构与此一致。"
fi

# ── Step 2: 构建前端 dist（frontend/Dockerfile 只做 COPY dist）─────
echo ""
echo "▶ [2/6] 构建前端静态文件（含 /chuilei/eval/ 前缀）..."
( cd "$PROJECT_ROOT/frontend" \
    && npm install --prefer-offline --no-audit --silent \
    && npm run build )
[ -d "$PROJECT_ROOT/frontend/dist" ] || { echo "❌ 前端构建失败，未生成 frontend/dist"; exit 1; }
echo "  ✅ 前端 dist 构建完成"

# ── Step 3: 构建三个镜像 ──────────────────────────────────────────
echo ""
echo "▶ [3/6] 构建 Docker 镜像（可能需要几分钟）..."

echo "  [3a] benchmark-eval:latest ..."
docker build -t benchmark-eval:latest \
    -f "$PROJECT_ROOT/deploy_docker/ais_bench/Dockerfile" "$PROJECT_ROOT"

echo "  [3b] score-backend:latest ..."
docker build -t score-backend:latest \
    -f "$PROJECT_ROOT/deploy_docker/backend/Dockerfile" "$PROJECT_ROOT"

echo "  [3c] score-frontend:latest ..."
docker build -t score-frontend:latest \
    -f "$PROJECT_ROOT/deploy_docker/frontend/Dockerfile" "$PROJECT_ROOT/frontend"
echo "  ✅ 三个镜像构建完成"

# ── Step 4: 导出镜像 ──────────────────────────────────────────────
echo ""
echo "▶ [4/6] 导出三个镜像为 ${IMAGES_FILE}（可能需要几分钟）..."

IMAGES_PATH="$OUTPUTS_DIR/$IMAGES_FILE"
docker save benchmark-eval:latest score-backend:latest score-frontend:latest \
    | gzip > "$IMAGES_PATH"
echo "  ✅ 镜像已导出: $IMAGES_PATH ($(du -sh "$IMAGES_PATH" | cut -f1))"

# ── Step 5: 组织部署目录 ──────────────────────────────────────────
echo ""
echo "▶ [5/6] 组织部署目录结构..."

rm -rf "$TMP_DIR"
mkdir -p "$PKG_DIR/code"

# 5.1 镜像包
cp "$IMAGES_PATH" "$PKG_DIR/$IMAGES_FILE"

# 5.2 业务脚本 code/ —— 后端起算子容器时 -v 挂载，必须完整
echo "  复制 code 业务脚本（eval_entry/eval_judge/scripts/ais_bench…）..."
cp "$PROJECT_ROOT/eval_entry.py"            "$PKG_DIR/code/"
cp "$PROJECT_ROOT/eval_judge.py"            "$PKG_DIR/code/"
[ -f "$PROJECT_ROOT/setup.py" ]                  && cp "$PROJECT_ROOT/setup.py"                  "$PKG_DIR/code/"
[ -f "$PROJECT_ROOT/README.md" ]                 && cp "$PROJECT_ROOT/README.md"                 "$PKG_DIR/code/"
[ -f "$PROJECT_ROOT/aggregate_eval_reports.py" ] && cp "$PROJECT_ROOT/aggregate_eval_reports.py" "$PKG_DIR/code/"
cp -r "$PROJECT_ROOT/scripts"   "$PKG_DIR/code/scripts"
cp -r "$PROJECT_ROOT/ais_bench" "$PKG_DIR/code/ais_bench"
# 清掉 python 缓存，减小体积
find "$PKG_DIR/code" -type d -name '__pycache__' -prune -exec rm -rf {} + 2>/dev/null || true
find "$PKG_DIR/code" -type f -name '*.pyc' -delete 2>/dev/null || true
echo "  ✅ code/ 已就绪 ($(du -sh "$PKG_DIR/code" | cut -f1))"

# 5.3 生产 docker-compose（后端端口收口，仅经 nginx 暴露）
cat > "$PKG_DIR/docker-compose.prod.yml" << 'COMPOSE_EOF'
# ── Score Platform 生产环境部署 ──────────────────────────────────
# 用法：
#   1. cp .env.example .env && vi .env   # 填 WORKSPACE_DIR / BACKEND_DATA_DIR
#   2. bash init_workspace.sh            # 铺 code + 建目录（读取 .env）
#   3. docker-compose -f docker-compose.prod.yml --env-file .env up -d
# 访问： http://<服务器IP>/chuilei/eval/
# ──────────────────────────────────────────────────────────────────

services:
  score-front:
    image: score-frontend:latest
    container_name: score-front
    ports:
      - "${FRONT_PORT:-8087}:80"   # 宿主机端口取自 .env 的 FRONT_PORT（默认 8087）；容器内 nginx 固定 80
    depends_on:
      - score-backend
    networks:
      - score-net

  score-backend:
    image: score-backend:latest
    container_name: score-backend
    # 端口收口：不映射到宿主机，仅同网络内 nginx 经 score-backend:8080 反代访问。
    # 如需临时直连后端调试，取消下面两行注释：
    # ports:
    #   - "8080:8080"
    expose:
      - "8080"
    volumes:
      # ★WORKSPACE_DIR 宿主机与容器内必须同路径（后端经 docker.sock 起算子容器，
      #   docker daemon 解析的是宿主机路径）
      - ${WORKSPACE_DIR}:${WORKSPACE_DIR}
      - ${BACKEND_DATA_DIR}:/opt/eval_backend_data
      - /var/run/docker.sock:/var/run/docker.sock
    environment:
      - EVAL_BACKEND_WORKSPACE_DIR=${WORKSPACE_DIR}
      - EVAL_BACKEND_BACKEND_DATA_DIR=/opt/eval_backend_data
      - EVAL_BACKEND_CODE_DIR=${WORKSPACE_DIR}/code
      - EVAL_BACKEND_ADMIN_USERNAME=${EVAL_BACKEND_ADMIN_USERNAME:-admin}
      - EVAL_BACKEND_ADMIN_PASSWORD=${EVAL_BACKEND_ADMIN_PASSWORD:-}
    networks:
      - score-net

networks:
  score-net:
    driver: bridge
COMPOSE_EOF

# 5.4 .env 模板
cat > "$PKG_DIR/.env.example" << 'ENV_EOF'
# ── Score Platform 生产环境配置 ──────────────────────────────────
# 复制为 .env 后填写实际值

# 前端对外端口（宿主机），按需修改；容器内 nginx 固定 80
FRONT_PORT=8087

# Workspace / 数据目录（宿主机绝对路径，容器内外保持一致）
WORKSPACE_DIR=/opt/eval_workspace
BACKEND_DATA_DIR=/opt/eval_backend_data

# 首次启动初始化的管理员账号（建库后改动请到平台内修改）
EVAL_BACKEND_ADMIN_USERNAME=admin
EVAL_BACKEND_ADMIN_PASSWORD=change_me_please

# 说明：被测/打分模型的 IP/端口/密钥不在此处配置，
#       部署后在 Web 界面「评测模型」「打分模型」中录入。
ENV_EOF

# 5.5 一键铺底脚本：建目录 + 拷 code 到 WORKSPACE_DIR/code
cat > "$PKG_DIR/init_workspace.sh" << 'INIT_EOF'
#!/usr/bin/env bash
# 读取同目录 .env，建好 workspace/backend_data 目录并把 code 铺到 WORKSPACE_DIR/code
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
[ -f "$HERE/.env" ] || { echo "❌ 未找到 .env，请先 cp .env.example .env 并填写"; exit 1; }
set -a; . "$HERE/.env"; set +a
: "${WORKSPACE_DIR:?请在 .env 中设置 WORKSPACE_DIR}"
: "${BACKEND_DATA_DIR:?请在 .env 中设置 BACKEND_DATA_DIR}"

mkdir -p "$WORKSPACE_DIR"/{data,outputs,code}
mkdir -p "$BACKEND_DATA_DIR"/{envs,logs}

echo "铺设业务脚本 → $WORKSPACE_DIR/code ..."
cp -r "$HERE/code/." "$WORKSPACE_DIR/code/"

echo "✅ 完成。目录结构："
echo "   WORKSPACE_DIR   = $WORKSPACE_DIR  (data/ outputs/ code/)"
echo "   BACKEND_DATA_DIR= $BACKEND_DATA_DIR (envs/ logs/ eval_backend.db)"
echo "下一步： docker-compose -f docker-compose.prod.yml --env-file .env up -d"
INIT_EOF
chmod +x "$PKG_DIR/init_workspace.sh"

# 5.6 部署说明
cat > "$PKG_DIR/README.txt" << 'README_EOF'
=== Score Platform 私域部署说明 ===

目录结构：
  score_platform/
  ├── score-platform-images.tar.gz   # 三个服务镜像离线包（aarch64）
  ├── docker-compose.prod.yml        # 生产 Compose（后端端口已收口，仅经 nginx 暴露）
  ├── .env.example                   # 环境变量模板
  ├── init_workspace.sh              # 一键建目录 + 铺 code 业务脚本
  ├── code/                          # 业务脚本（被后端挂进算子容器，必须完整）
  │   ├── eval_entry.py  eval_judge.py  setup.py
  │   ├── scripts/
  │   └── ais_bench/                 # 评测框架源码（-v 覆盖镜像内同名目录）
  └── README.txt

部署步骤（华为 910C / 任意 aarch64 Linux）：

  1. 导入镜像（benchmark-eval / score-backend / score-frontend 一次导入）：
       docker load < score-platform-images.tar.gz

  2. 配置：
       cp .env.example .env
       vi .env        # 填 WORKSPACE_DIR / BACKEND_DATA_DIR / 管理员密码

  3. 建目录并铺 code：
       bash init_workspace.sh

  4. 启动：
       docker-compose -f docker-compose.prod.yml --env-file .env up -d

  5. 访问（注意带前缀，裸 / 会 301 跳转）：
       http://<服务器IP>/chuilei/eval/

  6. 日志 / 状态：
       docker-compose -f docker-compose.prod.yml logs -f
       docker ps

要点：
  - benchmark-eval 由后端经 docker.sock 动态 docker run，无需在 compose 声明。
  - WORKSPACE_DIR 宿主机与容器内同路径，否则算子容器挂载失败。
  - 评测平台只是 HTTP 客户端，不吃 NPU；被测/打分模型为独立服务，
    910C 网络需能访问其 IP:PORT。
  - 备份只需备份 BACKEND_DATA_DIR/eval_backend.db（全部平台状态）。
  - 业务脚本改动直接编辑 WORKSPACE_DIR/code 下文件即可，无需重建镜像。
README_EOF

echo "  ✅ 部署目录已准备好"

# ── Step 6: 压缩打包 ──────────────────────────────────────────────
echo ""
echo "▶ [6/6] 压缩打包..."

FINAL_PACKAGE="$OUTPUTS_DIR/${PACKAGE_NAME}.tar.gz"
tar -czf "$FINAL_PACKAGE" -C "$TMP_DIR" "score_platform"
rm -rf "$TMP_DIR"

echo ""
echo "======================================================"
echo "  ✅ 打包完成！"
echo "  📦 $(du -sh "$FINAL_PACKAGE" | cut -f1) → $FINAL_PACKAGE"
echo ""
echo "  传输到私域服务器："
echo "    scp $FINAL_PACKAGE user@server:/opt/"
echo ""
echo "  服务器上执行："
echo "    cd /opt && tar -xzf ${PACKAGE_NAME}.tar.gz && cd score_platform"
echo "    docker load < score-platform-images.tar.gz"
echo "    cp .env.example .env && vi .env"
echo "    bash init_workspace.sh"
echo "    docker-compose -f docker-compose.prod.yml --env-file .env up -d"
echo "    # 访问 http://<服务器IP>/chuilei/eval/"
echo "======================================================"
