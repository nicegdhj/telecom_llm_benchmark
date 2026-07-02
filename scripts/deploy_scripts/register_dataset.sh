#!/bin/bash
# ── 数据集版本注册脚本 ────────────────────────────────────────────────
# 将已在磁盘上的 .jsonl 文件注册为数据集版本（无需通过前端上传）
# 适用场景：私域网络限制文件上传大小（如 >100MB），先手动传到服务器再注册
#
# ── 用法 ─────────────────────────────────────────────────────────────
#
# 【单条注册】
#   bash scripts/deploy_scripts/register_dataset.sh \
#       --task-key task_43_suite \
#       --tag v1 \
#       --file /data/task43.jsonl \
#       [--default] \
#       [--note "初始版本"]
#
# 【批量注册】读取 CSV 配置文件，一次注册多个任务
#   bash scripts/deploy_scripts/register_dataset.sh --batch /data/register_list.csv
#
# ── CSV 格式 ──────────────────────────────────────────────────────────
# 字段顺序固定：task_key,tag,file_path,is_default,note
# 第一行（标题/注释行）会自动跳过，空行忽略
#
#   task_key,tag,file_path,is_default,note
#   task_43_suite,v1,/data/task43.jsonl,true,初始版本
#   task_1_suite,v1,/data/task1.jsonl,true,初始版本
#   task_34_suite,v2,/data/task34_v2.jsonl,false,
#
# ── 可选参数 ──────────────────────────────────────────────────────────
#   --db        <path>   指定数据库路径（默认自动推导）
#   --workspace <path>   指定 workspace 路径（默认自动推导）
#   --default            将该版本设为默认（会清除同任务其他版本的默认标记）
#   --note      <text>   备注说明
#
# ── 注意事项 ──────────────────────────────────────────────────────────
# 1. 文件会复制到 workspace/data/versions/{task_key}/{tag}/data.jsonl
#    若源文件已在目标位置则跳过复制
# 2. 相同 task_key + tag 已存在时会原地更新，不会报错
# 3. 设为 --default 后，系统跑任务时优先使用该版本；
#    未设默认时，系统自动取最新上传的版本兜底
# ─────────────────────────────────────────────────────────────────────

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

DB_PATH="${EVAL_BACKEND_BACKEND_DATA_DIR:-$PROJECT_DIR/backend/backend_data}/eval_backend.db"
WORKSPACE="${WORKSPACE_DIR:-$PROJECT_DIR/workspace}"

# ── 工具函数 ──────────────────────────────────────────────────────────

die() { echo "❌ $*" >&2; exit 1; }

sha256_of() {
    if command -v sha256sum &>/dev/null; then
        sha256sum "$1" | awk '{print $1}'
    else
        shasum -a 256 "$1" | awk '{print $1}'
    fi
}

# 注册单条数据集版本
# 参数: task_key  tag  file_path  is_default(true/false)  note
register_one() {
    local task_key="$1"
    local tag="$2"
    local file_path="$3"
    local is_default="$4"   # true / false / 1 / 0
    local note="$5"

    # 规范化 is_default 为 1/0
    [[ "$is_default" == "true" || "$is_default" == "1" ]] && is_default=1 || is_default=0

    echo "──────────────────────────────────────────"
    echo "  任务: $task_key  标签: $tag"
    echo "  文件: $file_path"
    echo "  默认: $([[ $is_default == 1 ]] && echo 是 || echo 否)"
    [[ -n "$note" ]] && echo "  备注: $note"

    # 校验输入
    [[ -f "$file_path" ]] || die "文件不存在: $file_path"
    [[ "$DB_PATH" ]] && [[ -f "$DB_PATH" ]] || die "数据库不存在: $DB_PATH"

    # 查找 task_id
    local task_id
    task_id=$(sqlite3 "$DB_PATH" "SELECT id FROM tasks WHERE key='$task_key' LIMIT 1;")
    [[ -n "$task_id" ]] || die "任务不存在: $task_key（请先在系统中创建该任务）"

    # 检查 tag 是否已存在（存在则更新，否则插入）
    local existing_id
    existing_id=$(sqlite3 "$DB_PATH" "SELECT id FROM dataset_versions WHERE task_id=$task_id AND tag='$tag' LIMIT 1;")

    # 目标路径: workspace/data/versions/{task_key}/{tag}/data.jsonl
    local dest_dir="$WORKSPACE/data/versions/$task_key/$tag"
    local dest_file="$dest_dir/data.jsonl"
    mkdir -p "$dest_dir"

    # 若源文件和目标不是同一个，则复制
    if [[ "$(realpath "$file_path")" != "$(realpath "$dest_file" 2>/dev/null)" ]]; then
        cp "$file_path" "$dest_file"
        echo "  已复制到: $dest_file"
    else
        echo "  文件已在目标位置，跳过复制"
    fi

    # 计算 SHA256
    local hash
    hash=$(sha256_of "$dest_file")

    # 相对路径（相对于 workspace）
    local rel_path="data/versions/$task_key/$tag/data.jsonl"

    # 若设为默认，先清除该任务其他默认版本
    if [[ $is_default == 1 ]]; then
        sqlite3 "$DB_PATH" "UPDATE dataset_versions SET is_default=0 WHERE task_id=$task_id;"
    fi

    # 转义 note 中的单引号
    note="${note//\'/\'\'}"

    local now
    now=$(date -u +"%Y-%m-%d %H:%M:%S")

    if [[ -n "$existing_id" ]]; then
        sqlite3 "$DB_PATH" "
            UPDATE dataset_versions
            SET data_path='$rel_path', content_hash='$hash',
                is_default=$is_default, uploaded_at='$now', note='$note'
            WHERE id=$existing_id;
        "
        echo "  ✅ 已更新版本 (id=$existing_id)"
    else
        sqlite3 "$DB_PATH" "
            INSERT INTO dataset_versions (task_id, tag, data_path, content_hash, is_default, uploaded_at, note)
            VALUES ($task_id, '$tag', '$rel_path', '$hash', $is_default, '$now', '$note');
        "
        local new_id
        new_id=$(sqlite3 "$DB_PATH" "SELECT last_insert_rowid();")
        echo "  ✅ 已注册版本 (id=$new_id)"
    fi
}

# ── 参数解析 ──────────────────────────────────────────────────────────

BATCH_FILE=""
TASK_KEY=""
TAG=""
FILE_PATH=""
IS_DEFAULT="false"
NOTE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --db)         DB_PATH="$2";   shift 2 ;;
        --workspace)  WORKSPACE="$2"; shift 2 ;;
        --batch)      BATCH_FILE="$2"; shift 2 ;;
        --task-key)   TASK_KEY="$2";  shift 2 ;;
        --tag)        TAG="$2";       shift 2 ;;
        --file)       FILE_PATH="$2"; shift 2 ;;
        --default)    IS_DEFAULT="true"; shift ;;
        --note)       NOTE="$2";      shift 2 ;;
        -h|--help)
            sed -n '2,20p' "$0" | sed 's/^# \?//'
            exit 0 ;;
        *) die "未知参数: $1（使用 --help 查看帮助）" ;;
    esac
done

echo "========================================"
echo "  数据集版本注册"
echo "========================================"
echo "  数据库: $DB_PATH"
echo "  Workspace: $WORKSPACE"
echo ""

# ── 批量模式 ─────────────────────────────────────────────────────────

if [[ -n "$BATCH_FILE" ]]; then
    [[ -f "$BATCH_FILE" ]] || die "批量配置文件不存在: $BATCH_FILE"
    echo "📋 批量模式，读取: $BATCH_FILE"
    echo ""

    success=0
    fail=0
    while IFS=',' read -r bkey btag bfile bdefault bnote; do
        # 跳过注释行和标题行
        [[ "$bkey" =~ ^#   ]] && continue
        [[ "$bkey" =~ ^task_key ]] && continue
        [[ -z "$bkey"      ]] && continue

        # 去除首尾空格
        bkey="${bkey// /}"; btag="${btag// /}"
        bfile="$(echo "$bfile" | xargs)"
        bdefault="$(echo "$bdefault" | xargs)"
        bnote="$(echo "$bnote" | xargs)"

        if register_one "$bkey" "$btag" "$bfile" "${bdefault:-false}" "$bnote"; then
            ((success++)) || true
        else
            ((fail++)) || true
        fi
        echo ""
    done < "$BATCH_FILE"

    echo "========================================"
    echo "  完成: 成功 $success 条，失败 $fail 条"
    echo "========================================"
    exit 0
fi

# ── 单条模式 ─────────────────────────────────────────────────────────

[[ -n "$TASK_KEY" ]] || die "请指定 --task-key 或 --batch"
[[ -n "$TAG"      ]] || die "请指定 --tag"
[[ -n "$FILE_PATH" ]] || die "请指定 --file"

register_one "$TASK_KEY" "$TAG" "$FILE_PATH" "$IS_DEFAULT" "$NOTE"
echo ""
echo "========================================"
echo "  ✅ 注册完成"
echo "========================================"
