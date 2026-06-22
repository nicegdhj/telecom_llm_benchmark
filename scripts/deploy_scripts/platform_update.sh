#!/usr/bin/env bash
# ==============================================================================
# platform_update.sh —— Score Platform 唯一更新脚本（数据/版本解耦布局，见手册 §6.1）
#
# 一条命令完成：解压新包 → 软链共享数据根 .env → 备份数据库 → 导入新镜像 →
#              停旧容器 → 同步 code → 起新容器 → 健康检查 → 切换 current 软链。
# 业务数据全程待在数据根（BASE/score_data），不随版本走；升级前自动备份数据库。
#
# 约定布局（BASE 默认 = 本脚本所在目录）：
#   $BASE/
#   ├── platform_update.sh            ← 本脚本（建议常驻 BASE）
#   ├── score_data/                   数据根：.env / eval_workspace / eval_backend_data
#   ├── score_platform_<版本>/        各版本发布目录
#   └── score_platform_current ─→ 当前版本
#
# 用法：
#   bash platform_update.sh --pkg /path/score_platform_20260630_xxxx.tar.gz
#   bash platform_update.sh --pkg <包> --name score_platform_0630   # 自定义版本目录名
#   bash platform_update.sh --pkg <包> -y                           # 跳过确认
# 选项：--base <目录>（默认脚本所在目录）  --skip-backup（不推荐）  -h 帮助
# ==============================================================================
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
PKG=""; REL_NAME=""; BASE=""; ASSUME_YES=0; SKIP_BACKUP=0; MIN_FREE_GB=10

while [ $# -gt 0 ]; do
  case "$1" in
    --pkg)         PKG="$2"; shift 2;;
    --name)        REL_NAME="$2"; shift 2;;
    --base)        BASE="$2"; shift 2;;
    -y|--yes)      ASSUME_YES=1; shift;;
    --skip-backup) SKIP_BACKUP=1; shift;;
    -h|--help)     grep '^#' "$SELF" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "未知参数: $1（-h 查看用法）"; exit 2;;
  esac
done

log(){ echo "▶ $*"; }
ok(){ echo "  ✅ $*"; }
warn(){ echo "  ⚠️  $*"; }
die(){ echo "  ❌ $*" >&2; exit 1; }
confirm(){ [ "$ASSUME_YES" = 1 ] && return 0; read -r -p "  ➤ $* [y/N] " a; case "$a" in [yY]|[yY][eE][sS]) return 0;; *) return 1;; esac; }

if command -v docker-compose >/dev/null 2>&1; then DC=(docker-compose)
elif docker compose version >/dev/null 2>&1; then DC=(docker compose)
else die "未找到 docker-compose / docker compose"; fi

# ---- 1. 入参 & 前置检查 ----
log "[1/7] 前置检查"
[ -n "$PKG" ] || die "缺 --pkg <新版 tar.gz>"
[ -f "$PKG" ] || die "找不到包：$PKG"
command -v docker >/dev/null 2>&1 || die "未安装 docker"
docker info >/dev/null 2>&1 || die "docker daemon 未运行或当前用户无权访问"

[ -n "$BASE" ] || BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_ROOT="$BASE/score_data"
ENVF="$DATA_ROOT/.env"
[ -d "$DATA_ROOT" ] || die "数据根不存在：$DATA_ROOT
   本机尚未建立「数据/版本解耦」布局。首次部署见手册 §5；老布局迁移见 §11.5。"
[ -f "$ENVF" ] || die "数据根缺权威 .env：$ENVF（见手册 §6.1）"

set -a; . "$ENVF"; set +a
: "${WORKSPACE_DIR:?.env 未设置 WORKSPACE_DIR}"
: "${BACKEND_DATA_DIR:?.env 未设置 BACKEND_DATA_DIR}"
DB="$BACKEND_DATA_DIR/eval_backend.db"
[ -d "$BACKEND_DATA_DIR" ] || die "BACKEND_DATA_DIR 不存在：$BACKEND_DATA_DIR（.env 路径不对？）"

[ -n "$REL_NAME" ] || REL_NAME="$(basename "$PKG" .tar.gz)"
REL="$BASE/$REL_NAME"

HOST_ARCH="$(uname -m)"
[ "$HOST_ARCH" = aarch64 ] || [ "$HOST_ARCH" = arm64 ] || \
  warn "本机架构 $HOST_ARCH；若包是别的架构打的，启动会 exec format error"
AVAIL_GB=$(( $(df -Pk "$BASE" | awk 'NR==2{print $4}') / 1024 / 1024 ))
[ "$AVAIL_GB" -ge "$MIN_FREE_GB" ] || warn "可用磁盘仅 ${AVAIL_GB}GB（建议 ≥ ${MIN_FREE_GB}GB）"
ok "BASE=$BASE  数据根=$DATA_ROOT  新版本=$REL  (compose: ${DC[*]})"

RUN=$(docker ps --filter ancestor=benchmark-eval:latest -q | wc -l | tr -d ' ')
if [ "$RUN" != 0 ]; then
  warn "检测到 $RUN 个评测算子容器在运行，更新会中断它们（对应任务需重跑，已落库结果不受影响）"
  confirm "仍要继续？" || die "已取消"
fi

echo
log "将更新到：$REL（数据在 $DATA_ROOT 不动，升级前自动备份数据库）"
confirm "确认开始更新？" || die "已取消"

# ---- 2. 解压新包 + 软链共享 .env ----
log "[2/7] 解压新包 → $REL"
[ -e "$REL" ] && warn "$REL 已存在，将覆盖其中文件"
mkdir -p "$REL"
tar -xzf "$PKG" -C "$REL" --strip-components=1
for f in docker-compose.prod.yml score-platform-images.tar.gz init_workspace.sh code; do
  [ -e "$REL/$f" ] || die "新包内缺 $f（包不完整或太旧？）"
done
ln -sf "$ENVF" "$REL/.env"
# 自更新：把新包内的本脚本刷到 BASE，保证下次用的是最新版
[ -f "$REL/platform_update.sh" ] && cp -f "$REL/platform_update.sh" "$BASE/platform_update.sh" 2>/dev/null || true
ok "解压完成，.env 已软链共享数据根"

COMPOSE=("${DC[@]}" -f "$REL/docker-compose.prod.yml" --env-file "$REL/.env")

# ---- 3. 备份数据库 ----
log "[3/7] 备份数据库"
if [ "$SKIP_BACKUP" = 1 ]; then
  warn "按 --skip-backup 跳过备份（不推荐）"
elif [ -f "$DB" ]; then
  mkdir -p "$BACKEND_DATA_DIR/backups"
  BK="$BACKEND_DATA_DIR/backups/eval_backend_$(date +%Y%m%d_%H%M%S).db"
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB" ".backup '$BK'" || cp -p "$DB" "$BK"
    sqlite3 "$BK" "PRAGMA integrity_check;" | grep -q '^ok$' || die "备份完整性校验失败，已中止（原库未动）"
  else
    cp -p "$DB" "$BK"
  fi
  [ -s "$BK" ] || die "备份文件为空，已中止"
  ok "数据库已备份 → $BK ($(du -h "$BK" | cut -f1))"
else
  warn "无既有数据库可备份（首次建库由后端启动时自动完成）"
fi

# ---- 4. 导入新镜像 ----
log "[4/7] 导入新镜像（docker load）"
docker load < "$REL/score-platform-images.tar.gz"
ok "镜像已导入"

# ---- 5. 停旧容器 + 同步 code + 起新容器 ----
log "[5/7] 停旧容器 → 同步 code → 起新容器"
( cd "$REL" && "${COMPOSE[@]}" down ) || warn "down 返回非零（可能本就未运行），继续"
( cd "$REL" && bash init_workspace.sh )
( cd "$REL" && "${COMPOSE[@]}" up -d )
ok "新容器已启动"

# ---- 6. 健康检查 ----
log "[6/7] 健康检查"
URL="http://localhost:${FRONT_PORT:-8087}/chuilei/eval/api/v1/health"
HEALTHY=0
for _ in $(seq 1 30); do
  curl -fsS "$URL" >/dev/null 2>&1 && { HEALTHY=1; break; }
  sleep 2
done

# ---- 7. 切换 current ----
echo
if [ "$HEALTHY" = 1 ]; then
  ln -sfn "$REL" "$BASE/score_platform_current"
  echo "====================== ✅ 更新完成 ======================"
  echo "  访问     ： http://<本机IP>:${FRONT_PORT:-8087}/chuilei/eval/"
  echo "  当前版本 ： $BASE/score_platform_current → $REL"
  [ "${BK:-}" ] && echo "  数据库备份： $BK"
  echo "  保留上一版目录以便回滚；确认无误后旧版本可删。"
  echo "========================================================="
else
  echo "====================== ⚠️  健康检查未通过 ======================"
  warn "新版本起来了但健康检查 30 次超时，current 未切换（仍指向上一版）。"
  echo "  排查： ${COMPOSE[*]} ps ;  ${COMPOSE[*]} logs --tail=100 score-backend"
  echo "  回滚： cd <上一版目录> && ${DC[*]} -f docker-compose.prod.yml --env-file .env up -d"
  [ "${BK:-}" ] && echo "         如需还原数据库： cp '$BK' '$DB'"
  echo "==============================================================="
  exit 1
fi
