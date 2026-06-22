#!/usr/bin/env bash
# ==============================================================================
# upgrade.sh —— Score Platform 私域【在线升级】脚本（保留老数据）
#
# 在【私域机器】上、解压后的新版 score_platform/ 目录内执行：
#   bash upgrade.sh            # 交互确认
#   bash upgrade.sh -y         # 跳过确认（自动化）
#   bash upgrade.sh --skip-backup   # 不备份数据库（不推荐）
#
# 它做什么：
#   1. 前置安全检查（必备文件、docker、.env、磁盘空间、是否有评测在跑）
#   2. 备份当前数据库 eval_backend.db（带完整性校验）
#   3. 导入新镜像 → 停旧容器（保留挂载数据）→ 同步 code → 起新容器
#   4. 启动后健康检查；失败给出回滚指引
#
# 数据安全：业务数据全在宿主机挂载目录（BACKEND_DATA_DIR / WORKSPACE_DIR），
#   docker load 与不带 -v 的 down/up 都不会动它们；升级前仍自动备份数据库以防万一。
#   后端新版本启动会自动迁移数据库 schema（幂等），老数据原样保留。
# ==============================================================================
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SELF="$HERE/$(basename "${BASH_SOURCE[0]}")"
cd "$HERE"

COMPOSE_FILE="docker-compose.prod.yml"
IMAGES_FILE="score-platform-images.tar.gz"
ASSUME_YES=0
SKIP_BACKUP=0
MIN_FREE_GB=10

for a in "$@"; do
  case "$a" in
    -y|--yes)       ASSUME_YES=1 ;;
    --skip-backup)  SKIP_BACKUP=1 ;;
    -h|--help)      grep '^#' "$SELF" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "未知参数: $a（用 -h 查看用法）"; exit 2 ;;
  esac
done

log()  { echo "▶ $*"; }
ok()   { echo "  ✅ $*"; }
warn() { echo "  ⚠️  $*"; }
die()  { echo "  ❌ $*" >&2; exit 1; }

confirm() {
  [ "$ASSUME_YES" = 1 ] && return 0
  read -r -p "  ➤ $* [y/N] " ans
  case "$ans" in [yY]|[yY][eE][sS]) return 0 ;; *) return 1 ;; esac
}

# 选择 compose 命令（V1 docker-compose / V2 docker compose）
if command -v docker-compose >/dev/null 2>&1; then
  DC=(docker-compose)
elif docker compose version >/dev/null 2>&1; then
  DC=(docker compose)
else
  die "未找到 docker-compose / docker compose"
fi
COMPOSE=("${DC[@]}" -f "$COMPOSE_FILE" --env-file .env)

# ── 1. 前置安全检查 ────────────────────────────────────────────────
log "[1/6] 前置安全检查..."
command -v docker >/dev/null 2>&1 || die "未安装 docker"
docker info >/dev/null 2>&1 || die "docker daemon 未运行或当前用户无权访问"
for f in "$COMPOSE_FILE" "$IMAGES_FILE" "init_workspace.sh" ".env"; do
  [ -e "$HERE/$f" ] || die "当前目录缺少 $f —— 请在解压后的 score_platform/ 目录内运行，且已 cp .env.example .env 并填好"
done
[ -d "$HERE/code" ] || die "缺少 code/ 业务脚本目录"

# 载入 .env
set -a; . "$HERE/.env"; set +a
: "${WORKSPACE_DIR:?.env 未设置 WORKSPACE_DIR}"
: "${BACKEND_DATA_DIR:?.env 未设置 BACKEND_DATA_DIR}"
DB="$BACKEND_DATA_DIR/eval_backend.db"

# 这是升级而非首次部署：BACKEND_DATA_DIR 必须已存在
[ -d "$BACKEND_DATA_DIR" ] || die "BACKEND_DATA_DIR 不存在：$BACKEND_DATA_DIR
     这看起来是【首次部署】而非升级。请改用：bash init_workspace.sh && ${DC[*]} -f $COMPOSE_FILE --env-file .env up -d"
[ -f "$DB" ] || warn "未发现既有数据库 $DB（升级场景请先确认 .env 路径无误）"

# 数据/版本解耦检查：数据目录不应放在版本(发布)目录内，否则旧版目录删不得、版本与数据耦死
REL_DIR="$(readlink -f "$HERE" 2>/dev/null || echo "$HERE")"
for d in "$WORKSPACE_DIR" "$BACKEND_DATA_DIR"; do
  rd="$(readlink -f "$d" 2>/dev/null || echo "$d")"
  case "$rd/" in
    "$REL_DIR"/*)
      warn "数据目录 $d 位于版本目录 $REL_DIR 内 —— 建议迁到版本无关的固定路径（见手册 §6.1），否则该版本目录将无法清理" ;;
  esac
done

# 架构提示（跨架构镜像 load 后会在启动时 exec format error）
HOST_ARCH="$(uname -m)"
[ "$HOST_ARCH" = "aarch64" ] || [ "$HOST_ARCH" = "arm64" ] || \
  warn "本机架构为 $HOST_ARCH；若镜像包是在不同架构打的，启动会失败（exec format error）"

# 磁盘空间（数据库备份 + 新镜像导入）
AVAIL_KB="$(df -Pk "$BACKEND_DATA_DIR" | awk 'NR==2{print $4}')"
AVAIL_GB=$(( AVAIL_KB / 1024 / 1024 ))
[ "$AVAIL_GB" -ge "$MIN_FREE_GB" ] || warn "可用磁盘仅 ${AVAIL_GB}GB（建议 ≥ ${MIN_FREE_GB}GB）：镜像导入或备份可能失败"
ok "必备文件 / .env / docker 就绪（compose: ${DC[*]}，可用磁盘 ${AVAIL_GB}GB）"

# 是否有评测算子容器正在运行（down 会中断后端 Worker，正在跑的算子容器会变孤儿）
RUNNING_OPS="$(docker ps --filter ancestor=benchmark-eval:latest -q | wc -l | tr -d ' ')"
if [ "$RUNNING_OPS" != "0" ]; then
  warn "检测到 $RUNNING_OPS 个评测算子容器正在运行；升级会中断它们，需重跑对应任务"
  confirm "仍要继续升级？" || die "已取消。建议等评测跑完或在平台内停止后再升级"
fi

echo
log "即将升级：停止旧容器 → 导入新镜像 → 起新容器（业务数据保留在挂载目录）"
confirm "确认开始升级？" || die "已取消"

# ── 2. 备份数据库 ──────────────────────────────────────────────────
echo
log "[2/6] 备份数据库..."
if [ "$SKIP_BACKUP" = 1 ]; then
  warn "按 --skip-backup 跳过备份（不推荐）"
elif [ -f "$DB" ]; then
  BK_DIR="$BACKEND_DATA_DIR/backups"
  mkdir -p "$BK_DIR"
  TS="$(date +%Y%m%d_%H%M%S)"
  BK="$BK_DIR/eval_backend_${TS}.db"
  if command -v sqlite3 >/dev/null 2>&1; then
    sqlite3 "$DB" ".backup '$BK'" || cp -p "$DB" "$BK"
    if ! sqlite3 "$BK" "PRAGMA integrity_check;" | grep -q '^ok$'; then
      die "备份完整性校验失败，已中止升级（原库未动）"
    fi
  else
    cp -p "$DB" "$BK"
  fi
  [ -s "$BK" ] || die "备份文件为空，已中止升级"
  ok "数据库已备份 → $BK ($(du -h "$BK" | cut -f1))"
else
  warn "无既有数据库可备份（首次建库将由后端启动时自动完成）"
fi

# ── 3. 导入新镜像 ──────────────────────────────────────────────────
echo
log "[3/6] 导入新镜像（docker load）..."
docker load < "$IMAGES_FILE"
ok "镜像已导入"

# ── 4. 停旧容器（保留数据）────────────────────────────────────────
echo
log "[4/6] 停止旧容器（down，不带 -v，挂载数据不受影响）..."
"${COMPOSE[@]}" down || warn "down 返回非零（可能本就未运行），继续"
ok "旧容器已停止"

# ── 5. 同步 code + 起新容器 ────────────────────────────────────────
echo
log "[5/6] 同步业务脚本 code/ 并启动新容器..."
bash "$HERE/init_workspace.sh"
"${COMPOSE[@]}" up -d
ok "新容器已启动"

# ── 6. 健康检查 ────────────────────────────────────────────────────
echo
log "[6/6] 健康检查..."
URL="http://localhost:${FRONT_PORT:-8087}/chuilei/eval/api/v1/health"
HEALTHY=0
for _ in $(seq 1 30); do
  if curl -fsS "$URL" >/dev/null 2>&1; then HEALTHY=1; break; fi
  sleep 2
done

echo
if [ "$HEALTHY" = 1 ]; then
  echo "======================================================"
  echo "  ✅ 升级完成且健康检查通过"
  echo "     访问： http://<本机IP>:${FRONT_PORT:-8087}/chuilei/eval/"
  [ "${BK:-}" ] && echo "     数据库备份： $BK"
  echo "     （确认无误后可清理悬空镜像： docker image prune -f）"
  echo "======================================================"
else
  echo "======================================================"
  warn "健康检查未通过（30 次轮询超时）。请排查："
  echo "     ${COMPOSE[*]} ps"
  echo "     ${COMPOSE[*]} logs --tail=100 score-backend"
  echo
  warn "回滚（如新版本异常）："
  echo "     1) ${COMPOSE[*]} down"
  [ "${BK:-}" ] && echo "     2) 还原数据库： cp '$BK' '$DB'"
  echo "     3) docker load < <上一版本镜像包>  # 若已留存旧包"
  echo "     4) ${COMPOSE[*]} up -d"
  echo "======================================================"
  exit 1
fi
