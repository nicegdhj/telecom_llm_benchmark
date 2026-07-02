#!/usr/bin/env bash
# ==============================================================================
# import_dataset_version.sh —— 手动导入一个数据集版本（私域无法走 Web 上传时用）
#
# 安全限制不让走「任务与数据 → 上传数据集」时，本脚本等价完成上传后端做的两件事：
#   ① 把数据文件放到约定路径   $WORKSPACE_DIR/data/versions/<task_key>/<tag>/data.jsonl
#   ② 往数据库 dataset_versions 插一行记录（平台「看到」某版本只取决于此表，不扫盘）
# 做完后刷新「任务与数据」即可看到新版本，建测评时下拉也能选到；后端无需重启。
#
# 运行时机制（worker.py）：评测某 custom 任务时，若所选版本 data_path ≠ 内置固定路径，
# 会把固定路径 data/custom_task/task_<n>.jsonl 软链到本版本文件，ais_bench 照常读 → 跑得通。
#
# 用法（在私域机器、平台目录 BASE 下执行，BASE 默认=本脚本所在目录）：
#   bash import_dataset_version.sh --task task_43_suite --tag v2 --file /path/task_43_v2.jsonl
#   bash import_dataset_version.sh --task task_43_suite --tag v2 --file <jsonl> --default --note "二期数据"
# 选项：
#   --task <key>     任务文件全名（如 task_43_suite，必须全名，不可简写）          必填
#   --tag  <tag>     版本标签（同一任务内唯一，如 v2）                          必填
#   --file <jsonl>   源数据文件（.jsonl，每行结构须与内置同任务数据一致）        必填
#   --default        设为该任务默认版本（会清掉同任务其它默认）
#   --note  <text>   备注
#   --base  <目录>   平台目录（含 score_data/.env，默认=脚本所在目录）
#   --force          目标文件已存在时允许覆盖
#   -y / --yes       跳过确认
#   -h / --help      查看用法
# ==============================================================================
set -euo pipefail

SELF="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
TASK=""; TAG=""; SRC=""; NOTE=""; BASE=""; IS_DEFAULT=0; FORCE=0; ASSUME_YES=0

while [ $# -gt 0 ]; do
  case "$1" in
    --task)    TASK="$2"; shift 2;;
    --tag)     TAG="$2"; shift 2;;
    --file)    SRC="$2"; shift 2;;
    --note)    NOTE="$2"; shift 2;;
    --base)    BASE="$2"; shift 2;;
    --default) IS_DEFAULT=1; shift;;
    --force)   FORCE=1; shift;;
    -y|--yes)  ASSUME_YES=1; shift;;
    -h|--help) grep '^#' "$SELF" | sed 's/^# \{0,1\}//'; exit 0;;
    *) echo "未知参数: $1（-h 查看用法）"; exit 2;;
  esac
done

log(){ echo "▶ $*"; }
ok(){ echo "  ✅ $*"; }
warn(){ echo "  ⚠️  $*"; }
die(){ echo "  ❌ $*" >&2; exit 1; }
confirm(){
  [ "$ASSUME_YES" = 1 ] && return 0
  if [ -r /dev/tty ]; then
    read -r -p "  ➤ $* [y/N] " a </dev/tty
  else
    die "非交互环境无法确认；请加 -y 重新执行"
  fi
  case "$a" in [yY]|[yY][eE][sS]) return 0;; *) return 1;; esac
}

# ---- 1. 入参 & .env ----
log "[1/5] 前置检查"
[ -n "$TASK" ] || die "缺 --task"
[ -n "$TAG" ]  || die "缺 --tag"
[ -n "$SRC" ]  || die "缺 --file"
[ -f "$SRC" ]  || die "源文件不存在：$SRC"
case "$SRC" in *.jsonl) ;; *) die "仅支持 .jsonl 文件（与 Web 上传一致）";; esac
KEY="$TASK"   # 任务必须为文件全名（如 task_43_suite），不做简写补全

[ -n "$BASE" ] || BASE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ENVF="$BASE/score_data/.env"
[ -f "$ENVF" ] || die "找不到权威 .env：$ENVF
   请用 --base 指向平台目录（含 score_data/.env），如 --base /dpc/hejia/eval_platform"
set -a; . "$ENVF"; set +a
: "${WORKSPACE_DIR:?.env 未设置 WORKSPACE_DIR}"
: "${BACKEND_DATA_DIR:?.env 未设置 BACKEND_DATA_DIR}"
DB="$BACKEND_DATA_DIR/eval_backend.db"
[ -f "$DB" ] || die "数据库不存在：$DB"

# 选 SQL/校验引擎：私域宿主机通常无 python3，直接用 score-backend 容器的 python；
# 仅当容器未运行时回退到宿主机 python3（开发/本地场景）。DB 与数据目录均为 bind mount，
# 容器内外同路径，故容器内可直接读到下面 copy 进 WORKSPACE_DIR 的数据文件。
ENGINE=""; DB_FOR_PY="$DB"
if docker ps --format '{{.Names}}' 2>/dev/null | grep -qx score-backend; then
  ENGINE="container"; DB_FOR_PY="/opt/eval_backend_data/eval_backend.db"
elif python3 -c 'import sqlite3' >/dev/null 2>&1; then
  ENGINE="host"
else
  die "score-backend 容器未运行，且宿主机无 python3，无法写库（请先启动平台）"
fi
ok "KEY=$KEY  tag=$TAG  引擎=$ENGINE"
ok "WORKSPACE_DIR=$WORKSPACE_DIR"

# 统一的 python 执行器：脚本从 stdin 读，参数走环境变量（避免引号/注入问题）
run_py(){
  if [ "$ENGINE" = host ]; then
    DB_PATH="$DB_FOR_PY" TASK_KEY="$KEY" DSV_TAG="$TAG" DSV_PATH="${REL_PATH:-}" \
    DSV_HASH="${HASH:-}" DSV_DEFAULT="$IS_DEFAULT" DSV_NOTE="$NOTE" \
      python3 -
  else
    docker exec -i \
      -e DB_PATH="$DB_FOR_PY" -e TASK_KEY="$KEY" -e DSV_TAG="$TAG" -e DSV_PATH="${REL_PATH:-}" \
      -e DSV_HASH="${HASH:-}" -e DSV_DEFAULT="$IS_DEFAULT" -e DSV_NOTE="$NOTE" \
      score-backend python3 -
  fi
}

# 用所选引擎校验某 jsonl 文件首个非空行是否合法 JSON（容器内外同路径，路径直接可用）
validate_jsonl(){
  local f="$1"
  local py='import json,sys
with open(sys.argv[1],"rb") as fh:
    for line in fh:
        s=line.strip()
        if s:
            json.loads(s); break
    else:
        raise SystemExit(1)'
  if [ "$ENGINE" = host ]; then
    printf '%s' "$py" | python3 - "$f" 2>/dev/null
  else
    printf '%s' "$py" | docker exec -i score-backend python3 - "$f" 2>/dev/null
  fi
}

# ---- 2. 校验任务存在 & tag 不冲突（写文件前先查，避免留垃圾/误覆盖）----
log "[2/5] 校验任务与版本标签"
PRECHECK="$(run_py <<'PY'
import os, sqlite3, sys
con = sqlite3.connect(os.environ["DB_PATH"], timeout=30); cur = con.cursor()
key = os.environ["TASK_KEY"]
row = cur.execute("SELECT id FROM tasks WHERE key=?", (key,)).fetchone()
if not row:
    print("NO_TASK"); sys.exit(0)
tid = row[0]
dup = cur.execute("SELECT id FROM dataset_versions WHERE task_id=? AND tag=?",
                  (tid, os.environ["DSV_TAG"])).fetchone()
print("DUP" if dup else "OK", tid)
PY
)"
case "$PRECHECK" in
  NO_TASK*) die "数据库无此任务 key=${KEY}（确认任务名；列表见「任务与数据」页）";;
  DUP*)     die "该任务已存在 tag=$TAG 的版本；换个 tag，或先在平台删除旧版本";;
  OK*)      TID="${PRECHECK#OK }"; ok "任务 id=${TID}，tag=$TAG 可用";;
  *)        die "校验返回异常：$PRECHECK";;
esac

# ---- 3. 放数据文件到约定路径 ----
log "[3/5] 放置数据文件"
DEST_DIR="$WORKSPACE_DIR/data/versions/$KEY/$TAG"
DEST="$DEST_DIR/data.jsonl"
REL_PATH="data/versions/$KEY/$TAG/data.jsonl"   # data_path：相对 WORKSPACE_DIR
if [ -e "$DEST" ] && [ "$FORCE" != 1 ]; then
  die "目标已存在：${DEST}（加 --force 覆盖）"
fi

echo
log "将导入数据集版本："
echo "    任务      ：$KEY (id=$TID)"
echo "    版本 tag  ：$TAG$([ "$IS_DEFAULT" = 1 ] && echo '  [设为默认]')"
echo "    源文件    ：$SRC"
echo "    目标路径  ：$DEST"
echo "    data_path ：$REL_PATH"
confirm "确认导入？" || die "已取消"

mkdir -p "$DEST_DIR"
cp -f "$SRC" "$DEST"
chmod 644 "$DEST"; chmod 755 "$DEST_DIR" 2>/dev/null || true
# 文件就位后用引擎校验格式（容器内外同路径，能读到 DEST）；失败回滚
validate_jsonl "$DEST" || { rm -rf "$DEST_DIR"; die "数据不是合法 JSONL（首个非空行无法解析为 JSON），已回滚"; }
HASH="$( (sha256sum "$DEST" 2>/dev/null || shasum -a 256 "$DEST") | cut -d' ' -f1 )"
ok "已放置并通过 JSONL 校验，sha256=$HASH"

# ---- 5. 插入数据库记录（含默认版本互斥处理），失败则回滚文件 ----
log "[4/5] 写入数据库 dataset_versions"
RESULT="$(run_py <<'PY'
import os, sqlite3, sys, datetime
con = sqlite3.connect(os.environ["DB_PATH"], timeout=30); cur = con.cursor()
key = os.environ["TASK_KEY"]; tag = os.environ["DSV_TAG"]
tid = cur.execute("SELECT id FROM tasks WHERE key=?", (key,)).fetchone()[0]
if cur.execute("SELECT id FROM dataset_versions WHERE task_id=? AND tag=?", (tid, tag)).fetchone():
    print("DUP"); sys.exit(0)
is_default = os.environ.get("DSV_DEFAULT") == "1"
if is_default:
    cur.execute("UPDATE dataset_versions SET is_default=0 WHERE task_id=? AND is_default=1", (tid,))
cur.execute(
    "INSERT INTO dataset_versions (task_id, tag, data_path, content_hash, is_default, uploaded_at, note)"
    " VALUES (?,?,?,?,?,?,?)",
    (tid, tag, os.environ["DSV_PATH"], os.environ.get("DSV_HASH") or None,
     1 if is_default else 0,
     datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
     os.environ.get("DSV_NOTE") or None))
con.commit()
print("OK", cur.lastrowid)
PY
)"
case "$RESULT" in
  OK*) VID="${RESULT#OK }"; ok "已写入 dataset_versions id=$VID";;
  DUP) rm -rf "$DEST_DIR"; die "并发冲突：tag=$TAG 刚被占用，已回滚文件";;
  *)   rm -rf "$DEST_DIR"; die "写库失败，已回滚文件。输出：$RESULT";;
esac

# ---- 完成：列出该任务现有版本 ----
log "[5/5] 完成，当前该任务的版本列表："
run_py <<'PY'
import os, sqlite3
con = sqlite3.connect(os.environ["DB_PATH"], timeout=30); cur = con.cursor()
tid = cur.execute("SELECT id FROM tasks WHERE key=?", (os.environ["TASK_KEY"],)).fetchone()[0]
for r in cur.execute("SELECT tag, is_default, data_path FROM dataset_versions"
                     " WHERE task_id=? ORDER BY uploaded_at", (tid,)):
    print("    - %-12s %s  %s" % (r[0], "(默认)" if r[1] else "      ", r[2]))
PY

echo
echo "====================== ✅ 导入完成 ======================"
echo "  刷新「任务与数据 → ${KEY}」即可看到 tag=${TAG}（后端无需重启）"
echo "  建测评时在该任务的数据版本下拉中选择 $TAG 即可使用"
echo "========================================================="
