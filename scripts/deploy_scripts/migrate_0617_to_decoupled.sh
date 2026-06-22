#!/usr/bin/env bash
# ==============================================================================
# 一次性迁移：把「数据耦在版本目录内」的旧部署(0617) 迁到「数据/版本解耦」布局，
# 并升级到新版(0622)。数据零丢失（mv 同盘 + upgrade.sh 升级前自动备份数据库）。
#
# 迁移后布局：
#   /dpc/hejia/eval_platform/
#   ├── score_data/                 数据根（版本无关）：.env / eval_workspace / eval_backend_data
#   ├── score_platform_0622/        新版发布目录
#   └── score_platform_current ─→ score_platform_0622
#
# 用法：在 910C 上执行  bash migrate_0617_to_decoupled.sh
# ==============================================================================
set -euo pipefail

# ========================= 按你的实际情况确认/修改 =========================
OLD_DIR=/dpc/hejia/score_platform_0617                        # 旧发布目录(内含 eval_workspace/eval_backend_data/.env)
BASE=/dpc/hejia/eval_platform                                 # 新平台总目录
NEW_REL="$BASE/score_platform_0622"                           # 新版发布目录
PKG=/dpc/hejia/score_platform_20260622_105800.tar.gz         # 新版离线包路径（按实际位置改）
CUSTOM_SRC=""   # 可选：原始 custom 数据目录(其下有 custom_task/)，用于修复旧 bug 写坏的软链；留空则跳过
# =========================================================================

DATA_ROOT="$BASE/score_data"
WS="$DATA_ROOT/eval_workspace"
BD="$DATA_ROOT/eval_backend_data"
ENVF="$DATA_ROOT/.env"

log(){ echo "▶ $*"; }
ok(){ echo "  ✅ $*"; }
die(){ echo "  ❌ $*" >&2; exit 1; }

if command -v docker-compose >/dev/null 2>&1; then DC="docker-compose"
elif docker compose version >/dev/null 2>&1; then DC="docker compose"
else die "未找到 docker-compose / docker compose"; fi

# ---- 1. 前置检查 ----
log "[1/7] 前置检查"
command -v docker >/dev/null 2>&1 || die "未安装 docker"
docker info >/dev/null 2>&1 || die "docker daemon 未运行或无权访问"
[ -f "$PKG" ] || die "找不到新版离线包：$PKG（请改 PKG 变量）"
[ -d "$OLD_DIR" ] || die "找不到旧发布目录：$OLD_DIR"
[ -f "$OLD_DIR/.env" ] || die "旧目录缺 .env：$OLD_DIR/.env"
[ -f "$OLD_DIR/docker-compose.prod.yml" ] || die "旧目录缺 docker-compose.prod.yml"
ok "检查通过（compose: $DC）"

# 读旧 .env 拿到旧数据位置
set -a; . "$OLD_DIR/.env"; set +a
OLD_WS="${WORKSPACE_DIR:?旧 .env 无 WORKSPACE_DIR}"
OLD_BD="${BACKEND_DATA_DIR:?旧 .env 无 BACKEND_DATA_DIR}"
log "旧数据位置：WORKSPACE_DIR=$OLD_WS  BACKEND_DATA_DIR=$OLD_BD"

# ---- 2. 停旧容器（保留数据）----
log "[2/7] 停止旧容器"
( cd "$OLD_DIR" && $DC -f docker-compose.prod.yml --env-file .env down ) || true
ok "已停止"

# ---- 3. 迁移数据到数据根（幂等）----
log "[3/7] 迁移数据 → $DATA_ROOT"
mkdir -p "$DATA_ROOT"
if [ -e "$WS" ]; then ok "已存在 $WS，跳过 workspace 迁移"
else [ -d "$OLD_WS" ] || die "旧 workspace 不存在：$OLD_WS"; mv "$OLD_WS" "$WS"; ok "已迁移 eval_workspace"; fi
if [ -e "$BD" ]; then ok "已存在 $BD，跳过 backend_data 迁移"
else [ -d "$OLD_BD" ] || die "旧 backend_data 不存在：$OLD_BD"; mv "$OLD_BD" "$BD"; ok "已迁移 eval_backend_data"; fi

# ---- 4. 写权威 .env（数据路径指向数据根）----
log "[4/7] 写权威 .env → $ENVF"
cp "$OLD_DIR/.env" "$ENVF"
sed -i "s#^[[:space:]]*WORKSPACE_DIR=.*#WORKSPACE_DIR=$WS#; \
        s#^[[:space:]]*BACKEND_DATA_DIR=.*#BACKEND_DATA_DIR=$BD#" "$ENVF"
grep -E "WORKSPACE_DIR|BACKEND_DATA_DIR" "$ENVF"
ok "权威 .env 就绪"

# ---- 5. 解压新版 + 软链共享 .env ----
log "[5/7] 解压新版 → $NEW_REL"
mkdir -p "$NEW_REL"
tar -xzf "$PKG" -C "$NEW_REL" --strip-components=1
[ -f "$NEW_REL/upgrade.sh" ] || die "新包内无 upgrade.sh（包太旧？请用最新 prod_all.sh 出包）"
ln -sf "$ENVF" "$NEW_REL/.env"
ok "解压完成，.env 已软链共享数据根"

# ---- 6. 升级（备份库 → 导入镜像 → 停旧 → 同步 code → 起新 → 健康检查）----
log "[6/7] 执行升级"
( cd "$NEW_REL" && bash upgrade.sh -y )

# ---- 7. 修复旧 bug 写坏的 custom 数据软链 + current 软链 ----
log "[7/7] 收尾"
if [ -n "$CUSTOM_SRC" ]; then
  [ -d "$CUSTOM_SRC/custom_task" ] || die "CUSTOM_SRC 下无 custom_task/：$CUSTOM_SRC"
  find "$WS/data/custom_task" -type l -delete 2>/dev/null || true
  cp -r "$CUSTOM_SRC/custom_task/." "$WS/data/custom_task/"
  ok "custom_task 已重置（清掉旧 bug 软链 + 重拷原始数据）"
else
  echo "  ⚠️  CUSTOM_SRC 为空 → 跳过 custom 数据修复。"
  echo "      旧版本的 bug 可能已把 $WS/data/custom_task/ 下部分 task_*.jsonl 写成错误软链。"
  echo "      若 custom 任务评测报错，设 CUSTOM_SRC=<原始数据目录> 重跑本步，或手动："
  echo "        find $WS/data/custom_task -type l -delete"
  echo "        cp -r <原始数据目录>/custom_task/. $WS/data/custom_task/"
fi
ln -sfn "$NEW_REL" "$BASE/score_platform_current"
ok "current → $NEW_REL"

echo
echo "====================== 迁移+升级完成 ======================"
echo "  数据根   ：$DATA_ROOT   (.env / eval_workspace / eval_backend_data)"
echo "  当前版本 ：$BASE/score_platform_current → $NEW_REL"
echo "  验证："
echo "    cd $NEW_REL && $DC -f docker-compose.prod.yml ps"
echo "    curl -fsS http://localhost:\${FRONT_PORT:-8087}/chuilei/eval/api/v1/health"
echo "  旧目录 $OLD_DIR 现只剩部署包文件，确认无误后可删/归档。"
echo "=========================================================="
