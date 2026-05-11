#!/bin/bash

# ==============================================================================
# 自动化混合模型评测脚本 (基于 Docker 私域部署)
# 支持 SSH 断开后后台持续运行（nohup 模式）
#
# 运行模式：
#   推理+评测（默认）  :  先推理，再评测
#   --infer-only       :  只推理，不评测
#   --judge-only       :  只评测，需配合 --infer-task 指定已有推理任务
#
# 用法:
#   bash run_mixed_benchmark.sh [选项]
#
# 参数:
#   --workspace     评测工作目录（默认 /opt/eval_workspace）
#   --code-dir       业务代码目录（默认 <workspace>/code）
#   --image-tar      Docker 镜像 tar 包路径（可选）
#   --image-tag      Docker 镜像 tag（默认 benchmark-eval:latest）
#   --infer-only     只跑推理，不跑评测
#   --judge-only     只跑评测（需配合 --infer-task）
#   --infer-task     指定已有的推理任务ID（judge-only 时必填，支持前缀匹配自动选最新）
#   --skip-llm       跳过 LLM 打分（仅评测阶段生效）
#   --eval-version   评测版本号（默认 eval_init）
#   --name           Docker 容器名称（可选，用于方便识别容器）
#
# 示例:
#   # 推理+评测一起跑
#   bash run_mixed_benchmark.sh --workspace /data/eval --image-tar /data/benchmark-eval.tar.gz
#
#   # 只推理
#   bash run_mixed_benchmark.sh --workspace /data/eval --infer-only
#
#   # 只评测（基于已有推理结果，支持前缀匹配自动选最新）
#   bash run_mixed_benchmark.sh --workspace /data/eval --judge-only --infer-task mixed_eval_20260415_
#   bash run_mixed_benchmark.sh --workspace /data/eval --judge-only --infer-task mixed_eval_20260415_103052
# ==============================================================================

set -euo pipefail

# ── 默认变量 ─────────────────────────────────────────────────────────
WORKSPACE="./eval_workspace"
IMAGE_TAG="benchmark-eval:latest"
IMAGE_TAR=""
CODE_DIR=""
SKIP_LLM="false"
EVAL_VERSION="eval_init"
CONTAINER_NAME=""
MODEL_CONFIG="local_qwen"

RUN_MODE="all"
INFER_TASK_ID=""

# ── 参数解析 ─────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workspace)
            WORKSPACE="$2"
            shift 2
            ;;
        --code-dir)
            CODE_DIR="$2"
            shift 2
            ;;
        --image-tar)
            IMAGE_TAR="$2"
            shift 2
            ;;
        --image-tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --infer-only)
            RUN_MODE="infer"
            shift
            ;;
        --judge-only)
            RUN_MODE="judge"
            shift
            ;;
        --infer-task)
            INFER_TASK_ID="$2"
            shift 2
            ;;
        --skip-llm)
            SKIP_LLM="true"
            shift
            ;;
        --eval-version)
            EVAL_VERSION="$2"
            shift 2
            ;;
        --name)
            CONTAINER_NAME="$2"
            shift 2
            ;;
        -h|--help)
            sed -n '9,38p' "$0" | sed 's/^# //;s/^#//'
            exit 0
            ;;
        *)
            echo "❌ 未知参数: $1（使用 --help 查看用法）"
            exit 1
            ;;
    esac
done

# ── 基于 workspace 推导各子路径 ──────────────────────────────────────
ENV_FILE="${WORKSPACE}/.env"
DATA_DIR="${WORKSPACE}/data"
OUTPUT_DIR="${WORKSPACE}/outputs"
LOG_DIR="${WORKSPACE}/logs"
CODE_DIR="${CODE_DIR:-${WORKSPACE}/code}"

if [[ "$RUN_MODE" == "infer" ]] || [[ "$RUN_MODE" == "all" ]]; then
    TASK_ID="mixed_eval_$(date +%Y%m%d_%H%M%S)"
else
    if [[ -n "$INFER_TASK_ID" ]]; then
        # 按前缀匹配，取最新
        readarray -t MATCHING_TASKS < <(ls -1 "$LOG_DIR"/${INFER_TASK_ID}* 2>/dev/null || true)
        if [[ ${#MATCHING_TASKS[@]} -gt 0 ]]; then
            TASK_ID=$(basename "${MATCHING_TASKS[-1]}" .log)
            echo "📌 匹配到推理任务: $TASK_ID（从 ${#MATCHING_TASKS[@]} 个匹配项中选择最新的）"
        else
            echo "❌ 未找到匹配前缀 '$INFER_TASK_ID' 的推理任务"
            echo "   请确认推理任务已完成，日志位于: $LOG_DIR/"
            exit 1
        fi
    else
        # 未指定时自动选 logs/ 下最新的推理任务
        readarray -t ALL_TASKS < <(ls -1 "$LOG_DIR"/mixed_eval_*.log 2>/dev/null || true)
        if [[ ${#ALL_TASKS[@]} -gt 0 ]]; then
            TASK_ID=$(basename "${ALL_TASKS[-1]}" .log)
            echo "📌 自动选择最新推理任务: $TASK_ID"
        else
            echo "❌ 未找到任何推理任务，请确认 $LOG_DIR/ 下存在推理日志"
            echo "   或通过 --infer-task 手动指定任务ID"
            exit 1
        fi
    fi
fi
LOG_FILE="${LOG_DIR}/${TASK_ID}.log"

# ── 前置校验 ─────────────────────────────────────────────────────────
if [[ ! -f "${ENV_FILE}" ]]; then
    echo "❌ 找不到配置文件: ${ENV_FILE}"
    exit 1
fi

if [[ "$RUN_MODE" != "judge" ]]; then
    if [[ ! -f "${CODE_DIR}/eval_entry.py" ]]; then
        echo "❌ 找不到业务脚本: ${CODE_DIR}/eval_entry.py"
        echo "   请将 eval_entry.py 放置到 ${CODE_DIR}/ 目录下"
        exit 1
    fi

    if [[ ! -d "${CODE_DIR}/scripts" ]]; then
        echo "❌ 找不到 scripts 目录: ${CODE_DIR}/scripts"
        echo "   请将 scripts/ 目录放置到 ${CODE_DIR}/ 下"
        exit 1
    fi
fi

# ── Docker 镜像检测 & 自动 load ──────────────────────────────────────
if docker image inspect "${IMAGE_TAG}" > /dev/null 2>&1; then
    echo "✅ Docker 镜像已存在: ${IMAGE_TAG}，跳过 load"
elif [[ -n "${IMAGE_TAR}" ]]; then
    if [[ ! -f "${IMAGE_TAR}" ]]; then
        echo "❌ 找不到镜像包: ${IMAGE_TAR}"
        exit 1
    fi
    echo "📦 正在 load Docker 镜像: ${IMAGE_TAR} ..."
    docker load < "${IMAGE_TAR}"
    if [[ $? -ne 0 ]]; then
        echo "❌ Docker 镜像 load 失败，请检查 tar 包是否完整"
        exit 1
    fi
    echo "✅ 镜像 load 成功: ${IMAGE_TAG}"
else
    echo "❌ 镜像 ${IMAGE_TAG} 不存在，且未指定 --image-tar"
    echo "   请先构建镜像或通过 --image-tar 指定离线包路径"
    exit 1
fi

mkdir -p "${LOG_DIR}" "${OUTPUT_DIR}"

# ── 打印模式信息 ─────────────────────────────────────────────────────
case "$RUN_MODE" in
    infer)
        MODE_DESC="🚀 推理模式（仅推理，不评测）"
        ;;
    judge)
        MODE_DESC="📊 评测模式（仅评测，基于已有推理结果）"
        ;;
    all)
        MODE_DESC="🔄 完整模式（推理 + 评测）"
        ;;
esac

# ── 判断是否已在 nohup 后台中运行（避免二次套娃） ──────────────────
if [[ -z "${_EVAL_BACKGROUND:-}" ]]; then
    echo "🔄 以后台模式启动（SSH 断开后进程将持续运行）"
    echo "📂 工作目录: ${WORKSPACE}"
    echo "💻 代码目录: ${CODE_DIR}"
    echo "📄 日志文件: ${LOG_FILE}"
    echo "👀 实时查看日志: tail -f ${LOG_FILE}"
    echo "🛑 终止任务:     docker stop ${CONTAINER_NAME:-$(docker ps -q --filter ancestor=${IMAGE_TAG} | head -1)}"
    echo "---------------------------------------------------"
    echo "$MODE_DESC"
    echo "---------------------------------------------------"

    export _EVAL_BACKGROUND=1
    nohup bash "$0" \
        --workspace "${WORKSPACE}" \
        --code-dir "${CODE_DIR}" \
        --image-tag "${IMAGE_TAG}" \
        $( [[ -n "$IMAGE_TAR" ]] && echo "--image-tar ${IMAGE_TAR}" ) \
        $( [[ "$RUN_MODE" == "infer" ]] && echo "--infer-only" ) \
        $( [[ "$RUN_MODE" == "judge" ]] && echo "--judge-only --infer-task ${TASK_ID}" ) \
        $( [[ "$SKIP_LLM" == "true" ]] && echo "--skip-llm" ) \
        $( [[ -n "$EVAL_VERSION" ]] && echo "--eval-version ${EVAL_VERSION}" ) \
        $( [[ -n "$CONTAINER_NAME" ]] && echo "--name ${CONTAINER_NAME}" ) \
        > "${LOG_FILE}" 2>&1 &

    echo "✅ 后台 PID: $!，安全断开 SSH 即可。"
    exit 0
fi

# ── 以下是真正的执行逻辑（在 nohup 后台中执行） ────────────────────
echo "$MODE_DESC"
echo "🚀 Task ID: ${TASK_ID}"
echo "---------------------------------------------------"

DOCKER_common_args=(
    --rm
    --memory=128g
    --memory-swap=128g
    --shm-size=16g
    --env-file "${ENV_FILE}"
    -v "${DATA_DIR}:/app/data"
    -v "${OUTPUT_DIR}:/app/outputs"
    -v "${CODE_DIR}/eval_entry.py:/app/eval_entry.py"
    -v "${CODE_DIR}/eval_judge.py:/app/eval_judge.py"
    -v "${CODE_DIR}/scripts:/app/scripts"
    "${IMAGE_TAG}"
)

# ── 从 .env 加载模型信息（shell 侧读取，用于显式传参）────────────
set +e; set -a; source "${ENV_FILE}" 2>/dev/null; set +a; set -e
# 根据 model-config 类型选择对应的环境变量
case "${MODEL_CONFIG}" in
    common_gateway)
        MODEL_NAME="${COMMON_MODEL_NAME:-unknown}"
        CONCURRENCY="${COMMON_CONCURRENCY:-5}"
        ;;
    maas|maas_gateway)
        MODEL_NAME="${MAAS_MODEL:-unknown}"
        CONCURRENCY="${MAAS_CONCURRENCY:-5}"
        ;;
    *)
        MODEL_NAME="${LOCAL_MODEL_NAME:-unknown}"
        CONCURRENCY="${LOCAL_CONCURRENCY:-20}"
        ;;
esac

# ── 阶段 1：推理（infer 或 all 模式）────────────────────────────────
if [[ "$RUN_MODE" == "infer" ]] || [[ "$RUN_MODE" == "all" ]]; then
    echo ""
    echo "📌 阶段 1/2：执行推理..."
    echo "---------------------------------------------------"

    INFER_NAME_ARG=()
    if [[ -n "$CONTAINER_NAME" ]]; then
        INFER_SUFFIX=$( [[ "$RUN_MODE" == "all" ]] && echo "all-infer" || echo "infer" )
        INFER_NAME_ARG=(--name "${CONTAINER_NAME}-${INFER_SUFFIX}")
    fi

    docker run "${INFER_NAME_ARG[@]}" "${DOCKER_common_args[@]}" \
        python eval_entry.py \
            --task-id "${TASK_ID}" \
            --model "${MODEL_NAME}" \
            --concurrency "${CONCURRENCY}" \
            --model-config "${MODEL_CONFIG}" \
            --tasks 1 34 36 43 44 60 101 102 \
            --generic-datasets \
                ceval_gen_0_shot_str \
                mmlu_redux_gen_5_shot_str \
                teledata_gen_0_shot \
                gpqa_gen_0_shot_str \
                bbh_gen_3_shot_cot_chat \
                BFCL_gen_simple \
                ifeval_0_shot_gen_str \
                math500_gen_0_shot_cot_chat_prompt \
                aime2025_gen_0_shot_chat_prompt \
                telemath_gen_0_cot_shot \
                teleqna_gen_0_shot \
                tspec_gen_0_shot \
                telequad_gen_0_shot \
                tele_exam_gen_0_shot \
                tele_exam_gen_0_shot_str \
                opseval_gen_0_shot \
                identity_gen_0_shot \
                exam_gen_0_shot


    INFER_RC=$?
    if [[ ${INFER_RC} -ne 0 ]]; then
        echo "==================================================="
        echo "❌ 推理阶段出现异常（退出码: ${INFER_RC}）"
        echo "==================================================="
        exit ${INFER_RC}
    fi

    echo ""
    echo "✅ 推理阶段完成"
fi

# ── 阶段 2：评测（judge 或 all 模式）─────────────────────────────────
if [[ "$RUN_MODE" == "judge" ]] || [[ "$RUN_MODE" == "all" ]]; then
    echo ""
    echo "📌 阶段 2/2：执行评测..."
    echo "---------------------------------------------------"

    JUDGE_NAME_ARG=()
    if [[ -n "$CONTAINER_NAME" ]]; then
        JUDGE_SUFFIX=$( [[ "$RUN_MODE" == "all" ]] && echo "all-judge" || echo "judge" )
        JUDGE_NAME_ARG=(--name "${CONTAINER_NAME}-${JUDGE_SUFFIX}")
    fi

    docker run "${JUDGE_NAME_ARG[@]}" "${DOCKER_common_args[@]}" \
        python eval_judge.py \
            --infer-task "${TASK_ID}" \
            --eval-version "${EVAL_VERSION}" \
            $( [[ "$SKIP_LLM" == "true" ]] && echo "--skip-llm" )

    if [[ $? -eq 0 ]]; then
        echo "==================================================="
        echo "✅ 评测流水线全部执行完成！"
        echo "📊 报告路径: ${OUTPUT_DIR}/${TASK_ID}/eval_*/report.md"
        echo "==================================================="
    else
        echo "==================================================="
        echo "❌ 评测阶段出现异常，请检查详情日志。"
        echo "==================================================="
        exit 1
    fi
fi