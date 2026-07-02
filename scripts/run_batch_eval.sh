#!/usr/bin/env bash
# ==============================================================================
# run_batch_eval.sh —— 批量重新评测 fmt/ 下所有实验组（支持本地 / Docker 两种模式）
#
# 功能：
#   1. 自动为缺少 infer_meta.json 的目录执行迁移（migrate）
#   2. 遍历 FMT_DIR 下所有子目录，调用 eval_judge.py 执行评测
#   3. 跳过已存在同名 eval_version 目录的组（避免重复）
#
# 模式：
#   --local         直接调 python eval_judge.py（本地开发机，默认）
#   --docker        通过 docker run 调用（私域服务器）
#
# 用法：
#   # 本地开发机
#   bash scripts/run_batch_eval.sh --fmt-dir /path/to/fmt
#
#   # 私域服务器（Docker 模式）
#   bash scripts/run_batch_eval.sh \
#       --docker \
#       --workspace /opt/eval_workspace \
#       --fmt-dir /opt/eval_workspace/fmt
#
#   # 只评测指定任务 + dry-run
#   bash scripts/run_batch_eval.sh --dry-run \
#       --eval-tasks "task_1_suite task_34_suite ceval_gen_0_shot_str"
# ==============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# ── 默认参数 ─────────────────────────────────────────────────────────────────
FMT_DIR="fmt"
EVAL_VERSION="eval_v4"
CONCURRENCY=10

# livecodebench_0_shot_chat_v6
#EVAL_TASKS="task_1_suite task_34_suite task_36_suite task_43_suite task_44_suite task_60_suite"

#EVAL_TASKS="teledata_gen_0_shot telequad_gen_0_shot"
EVAL_TASKS="exam_gen_0_shot"
#EVAL_TASKS="opseval_gen_0_shot exam_gen_0_shot"
#EVAL_TASKS="task_1_suite task_34_suite task_36_suite task_43_suite task_44_suite task_60_suite mmlu_redux_gen_5_shot_str ceval_gen_0_shot_str gpqa_gen_0_shot_str bbh_gen_3_shot_cot_chat BFCL_gen_simple ifeval_0_shot_gen_str math500_gen_0_shot_cot_chat_prompt aime2025_gen_0_shot_chat_prompt humaneval_gen_0_shot telemath_gen_0_cot_shot teleqna_gen_0_shot tspec_gen_0_shot tele_exam_gen_0_shot identity_gen_0_shot tele_exam_gen_0_shot_str telequad_gen_0_shot teledata_gen_0_shot exam_gen_0_shot opseval_gen_0_shot"
DRY_RUN=false
MODE="local"           # local | docker
WORKSPACE=""           # Docker 模式下的工作目录
CODE_DIR=""            # Docker 模式下的代码目录
IMAGE_TAG="benchmark-eval:latest"
ENV_FILE=""
DATA_DIR=""
MODEL_CONFIG="local_qwen"
TASK_TIMEOUT=7200
SKIP_MIGRATE=false

# ── 参数解析 ──────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --fmt-dir)       FMT_DIR="$2";       shift 2 ;;
        --version)       EVAL_VERSION="$2";  shift 2 ;;
        --score-worker-concurrency) CONCURRENCY="$2"; shift 2 ;;
        --eval-tasks)    EVAL_TASKS="$2";    shift 2 ;;
        --dry-run)       DRY_RUN=true;       shift 1 ;;
        --local)         MODE="local";       shift 1 ;;
        --docker)        MODE="docker";      shift 1 ;;
        --workspace)     WORKSPACE="$2";     shift 2 ;;
        --code-dir)      CODE_DIR="$2";      shift 2 ;;
        --image-tag)     IMAGE_TAG="$2";     shift 2 ;;
        --model-config)  MODEL_CONFIG="$2";  shift 2 ;;
        --task-timeout)  TASK_TIMEOUT="$2";  shift 2 ;;
        --skip-migrate)  SKIP_MIGRATE=true;  shift 1 ;;
        *) echo "❌ 未知参数: $1"; exit 1 ;;
    esac
done

# ── 推导默认路径 ──────────────────────────────────────────────────────────────
if [ "$MODE" = "docker" ]; then
    WORKSPACE="${WORKSPACE:-/opt/eval_workspace}"
    CODE_DIR="${CODE_DIR:-${WORKSPACE}/code}"
    FMT_DIR="${FMT_DIR:-${WORKSPACE}/fmt}"
    ENV_FILE="${WORKSPACE}/.env"
    DATA_DIR="${WORKSPACE}/data"

    # 校验
    [ -f "$ENV_FILE" ]                  || { echo "❌ 找不到 ${ENV_FILE}"; exit 1; }
    [ -f "$CODE_DIR/eval_judge.py" ]    || { echo "❌ 找不到 ${CODE_DIR}/eval_judge.py"; exit 1; }
    docker image inspect "$IMAGE_TAG" > /dev/null 2>&1 || { echo "❌ Docker 镜像不存在: $IMAGE_TAG"; exit 1; }
else
    FMT_DIR="${FMT_DIR:-/Users/jia/MyProjects/pythonProjects/cmcc_cxy/Bprocss/fmt}"
fi

[ -d "$FMT_DIR" ] || { echo "❌ fmt 目录不存在: $FMT_DIR"; exit 1; }

echo "======================================================"
echo "  批量评测脚本"
echo "  模式      : $MODE"
echo "  fmt 目录  : $FMT_DIR"
echo "  版本号    : $EVAL_VERSION"
echo "  并发数    : $CONCURRENCY"
echo "  评测任务  : ${EVAL_TASKS:-'全部（自动排序）'}"
[ "$MODE" = "docker" ] && echo "  工作目录  : $WORKSPACE"
[ "$MODE" = "docker" ] && echo "  镜像      : $IMAGE_TAG"
echo "  Dry-run   : $DRY_RUN"
echo "======================================================"

# ── Step 0: 自动 migrate（为缺少 infer_meta.json 的目录生成） ────────────────
if ! $SKIP_MIGRATE; then
    need_migrate=0
    for dir in "$FMT_DIR"/*/; do
        [ -d "$dir" ] || continue
        if [ -f "$dir/report.json" ] && [ ! -f "$dir/infer_meta.json" ]; then
            need_migrate=$((need_migrate + 1))
        fi
    done

    if [ $need_migrate -gt 0 ]; then
        echo ""
        echo "🔄 发现 $need_migrate 个目录缺少 infer_meta.json，自动执行迁移..."
        if $DRY_RUN; then
            echo "  [dry-run] 跳过迁移"
        elif [ "$MODE" = "docker" ]; then
            docker run --rm \
                -v "${FMT_DIR}:/data/fmt" \
                -v "${CODE_DIR}/scripts:/app/scripts" \
                "${IMAGE_TAG}" \
                python scripts/migrate_fmt_to_infer_meta.py /data/fmt --all --model-config "$MODEL_CONFIG"
        else
            python "$PROJECT_ROOT/scripts/migrate_fmt_to_infer_meta.py" "$FMT_DIR" --all --model-config "$MODEL_CONFIG"
        fi
        echo ""
    fi
fi

# ── 扫描目录 ──────────────────────────────────────────────────────────────────
candidates=()
skipped_no_meta=()
skipped_exists=()

for dir in "$FMT_DIR"/*/; do
    [ -d "$dir" ] || continue
    name=$(basename "$dir")

    if [ ! -f "$dir/infer_meta.json" ]; then
        skipped_no_meta+=("$name")
        continue
    fi

    if [ -d "$dir/$EVAL_VERSION" ]; then
        skipped_exists+=("$name")
        continue
    fi

    candidates+=("$name")
done

echo ""
echo "📋 待评测 (${#candidates[@]} 个):"
for c in "${candidates[@]}"; do echo "   - $c"; done

if [ ${#skipped_no_meta[@]} -gt 0 ]; then
    echo ""
    echo "⚠️  跳过（无 infer_meta.json，${#skipped_no_meta[@]} 个）:"
    for c in "${skipped_no_meta[@]}"; do echo "   - $c"; done
fi

if [ ${#skipped_exists[@]} -gt 0 ]; then
    echo ""
    echo "⏭️  跳过（$EVAL_VERSION 已存在，${#skipped_exists[@]} 个）:"
    for c in "${skipped_exists[@]}"; do echo "   - $c"; done
fi

if [ ${#candidates[@]} -eq 0 ]; then
    echo ""
    echo "✅ 无需执行（所有目录已完成或无 infer_meta.json）"
    exit 0
fi

echo ""
read -rp "确认开始批量评测？(y/N) " confirm
[[ "$confirm" =~ ^[Yy]$ ]] || { echo "已取消"; exit 0; }

# ── 批量执行 ──────────────────────────────────────────────────────────────────
success=0
failed=0
failed_list=()

for name in "${candidates[@]}"; do
    echo ""
    echo "────────────────────────────────────────────────────"
    echo "▶ [$((success + failed + 1))/${#candidates[@]}] $name"

    eval_tasks_args=""
    if [ -n "$EVAL_TASKS" ]; then
        eval_tasks_args="--eval-tasks $EVAL_TASKS"
    fi

    if [ "$MODE" = "docker" ]; then
        cmd="docker run --rm \
            --memory=128g --memory-swap=128g --shm-size=16g \
            --env-file ${ENV_FILE} \
            -v ${DATA_DIR}:/app/data \
            -v ${FMT_DIR}:/data/fmt \
            -v ${CODE_DIR}/eval_judge.py:/app/eval_judge.py \
            -v ${CODE_DIR}/scripts:/app/scripts \
            ${IMAGE_TAG} \
            python eval_judge.py \
                --infer-task ${name} \
                --output-dir /data/fmt \
                --eval-version ${EVAL_VERSION} \
                --score-worker-concurrency ${CONCURRENCY} \
                --task-timeout ${TASK_TIMEOUT} \
                ${eval_tasks_args}"
    else
        cmd="python ${PROJECT_ROOT}/eval_judge.py \
            --infer-task ${name} \
            --output-dir ${FMT_DIR} \
            --eval-version ${EVAL_VERSION} \
            --score-worker-concurrency ${CONCURRENCY} \
            --task-timeout ${TASK_TIMEOUT} \
            ${eval_tasks_args}"
    fi

    echo "  CMD: $cmd"

    if $DRY_RUN; then
        echo "  [dry-run] 跳过实际执行"
        success=$((success + 1))
        continue
    fi

    if eval "$cmd"; then
        success=$((success + 1))
        echo "  ✅ 完成: $name"
    else
        failed=$((failed + 1))
        failed_list+=("$name")
        echo "  ❌ 失败: $name（继续处理下一个）"
    fi
done

# ── 最终汇总 ──────────────────────────────────────────────────────────────────
echo ""
echo "======================================================"
echo "  批量评测完成"
echo "  成功: $success  失败: $failed"
if [ ${#failed_list[@]} -gt 0 ]; then
    echo "  失败列表:"
    for f in "${failed_list[@]}"; do echo "    - $f"; done
fi
echo ""
echo "  下一步：汇总结果"
if [ "$MODE" = "docker" ]; then
    echo "  docker run --rm \\"
    echo "      -v ${FMT_DIR}:/data/fmt \\"
    echo "      -v ${CODE_DIR}:/app/code \\"
    echo "      -v ${WORKSPACE}/outputs:/app/outputs \\"
    echo "      ${IMAGE_TAG} \\"
    echo "      python code/aggregate_eval_reports.py \\"
    echo "          --fmt-dir /data/fmt --eval-version ${EVAL_VERSION} \\"
    echo "          --output-dir /app/outputs"
else
    echo "  python aggregate_eval_reports.py \\"
    echo "      --fmt-dir ${FMT_DIR} --eval-version ${EVAL_VERSION}"
fi
echo "======================================================"

[ $failed -eq 0 ] || exit 1
