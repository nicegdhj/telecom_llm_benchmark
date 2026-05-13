#!/usr/bin/env bash
# ==============================================================================
# 多容器批量部署执行脚本 v3 (支持多变量注入)
#
# 作用：批量部署多个评测目标，每个目标独立工作区，通过共享 data/code/ 减少资源占用
#
# 与 v2 的区别：
#   - TARGETS 格式升级为：目录名:端口号:模型名:IP
#   - 支持注入 LOCAL_MODEL_NAME、LOCAL_HOST_IP、LOCAL_HOST_PORT 三个变量
#   - 支持三种运行模式：推理+评测、仅推理、仅评测
#   - 支持通过 EVAL_VERSION 指定评测版本号
#
# ==============================================================================
# 前置条件
# ==============================================================================
# 在 DEPLOY_ROOT 目录下需有一份解压好的 eval_workspace_*，包含：
#   eval_workspace_*/
#   ├── .env                  # 作为模板（每个目标会复制一份独立修改）
#   ├── data/                 # 共享数据（符号链接到各目标）
#   ├── code/                 # 共享代码
#   ├── run_mixed_benchmark.sh
#   └── benchmark-eval.tar.gz # 可选，镜像离线包
#
# ==============================================================================
# 配置区（修改这里来适配你的环境）
# ==============================================================================

# 1. 基础工作区：已解压的 eval_workspace 目录
#    留空则自动查找 DEPLOY_ROOT 下的第一个 eval_workspace_* 目录
BASE_WORKSPACE=""

# 2. 部署根目录：各目标工作区在此目录下创建（默认当前目录）
DEPLOY_ROOT="$(pwd)"

# 3. 默认模型服务 IP（单个目标未指定时使用此值）
DEFAULT_LOCAL_HOST_IP=""

# 4. 默认模型名称（单个目标未指定时使用此值）
DEFAULT_LOCAL_MODEL_NAME=""

# 5. 运行模式（3种）：
#    infer       : 推理 + 评测（默认）
#    infer-only  : 只跑推理，不评测
#    judge-only  : 只跑评测（需先有推理结果）
RUN_MODE="infer"

# 6. 推理任务ID（judge-only 模式时使用）：
#    - 完整 task_id：如 "mixed_eval_20260415_103052"
#    - 前缀匹配  ：如 "mixed_eval_20260415_" 会自动选择该前缀下最新的任务
#    - 留空      ：自动查找 logs/ 目录下最新的推理任务
INFER_TASK_ID=""

# 7. 评测版本号（用于指定评测方法，如 eval_init、eval_v2 等）
EVAL_VERSION="eval_init"

# 8. 定义目标：目录名:端口号:模型名:IP（后两项可留空使用默认值）
#    格式说明：
#      目录名   - 工作区目录名（会自动创建在 DEPLOY_ROOT 下）
#      端口号   - 模型服务的端口（必须）
#      模型名   - 留空则使用 DEFAULT_LOCAL_MODEL_NAME
#      IP       - 留空则使用 DEFAULT_LOCAL_HOST_IP
TARGETS=(
#      "pt_v_03:10051:qwen3-32b:188.109.35.155"
      "qwen3-32b_alarm:30018:qwen3-32b_alarm:188.109.35.149"
      "qwen3-32b-think:10051:qwen3-32b:188.109.35.148"
#     "telechat_36b:10052:telechat-36b:188.109.35.152"
     #"pt1_9_set81_think:10052:qwen3-32b:188.109.35.195"
     # "deepseek_3_1:0:deepseek_V3_1:188.109.35.100"
#     "pt_5000_ckpt_think:10051:qwen3-32b:188.109.35.152"
#     "pt_5000_ckpt_nothink:10052:qwen3-32b:188.109.35.152"
#     "pt_v02:6380:qwen3-32b-v2:188.109.35.147"
#     "pt_v02_grpo_global_step_100:6380:qwen3-32b-0421-global-step-100:188.109.35.148"
#     "pt_v02_grpo_global_step_207:6380:qwen3-32b-0421-global-step-207:188.109.35.149"

      #"gemma-4-31b:10051:gemma:188.109.35.152"
      #"glm-4-7-flash:10052:glm:188.109.35.152"
      #"telechat-36b:10053:telechat:188.109.35.152"
      #"qwen3-235b-think:30012:qwen3-235b:188.109.35.153"
      #"qwen3-32b-think:10051:qwen3-32b:188.109.35.159"
      #"qwen3-5-27b-think:10052:qwen3-27b:188.109.35.159"

#待测评
#    "qwen3_5_27b_think:9091:qwen3-27b:188.109.35.147"
#    "qwen3_32b_think:10051:qwen3-32b:188.109.35.147"
#    "pt1_9_set81_think:10051:qwen3-32b:188.109.35.150"
#    "pt1_9_set81_nothink:10052:qwen3-32b:188.109.35.150"
#    "pt3_7_set86_think:10051:qwen3-32b:188.109.35.152"
#    "pt3_7_set86_nothink:10052:qwen3-32b:188.109.35.152"
#    "qwen3_32b_nothink:10051:qwen3-32b:188.109.35.147"
#    "qwen3_235b_think:30012:qwen3-235b:188.109.35.150"
)

# ==============================================================================
# 使用示例
# ==============================================================================
#
# 【场景1】推理+评测一起跑
# -----------------------------------------------------------------------------
# 配置：
#   RUN_MODE="infer"
#   TARGETS 中配置好端口、模型名、IP
# 执行：
#   bash multi_deploy_benchmark_v3.sh
# 效果：
#   每个目标先推理，推理完成后自动执行评测
#
# -----------------------------------------------------------------------------
#
# 【场景2】只跑推理（批量推理，数据量大的情况）
# -----------------------------------------------------------------------------
# 配置：
#   RUN_MODE="infer-only"
#   TARGETS 中配置好端口、模型名、IP
# 执行：
#   bash multi_deploy_benchmark_v3.sh
# 效果：
#   所有目标只执行推理阶段，不评测
#   适合：推理耗时长、想先集中跑完推理的情况
#
# 之后可以单独跑评测：
#   RUN_MODE="judge-only"
#   INFER_TASK_ID="mixed_eval_20260415_"
#   bash multi_deploy_benchmark_v3.sh
#
# -----------------------------------------------------------------------------
#
# 【场景3】只跑评测（基于已有的推理结果）
# -----------------------------------------------------------------------------
# 配置：
#   RUN_MODE="judge-only"
#   INFER_TASK_ID="mixed_eval_20260415_"   # 前缀匹配，自动选最新
#   或
#   INFER_TASK_ID="mixed_eval_20260415_103052"  # 指定完整task_id
#   EVAL_VERSION="eval_v2"   # 指定评测版本号（可选，默认 eval_init）
# 执行：
#   bash multi_deploy_benchmark_v3.sh
# 效果：
#   所有目标只执行评测阶段，使用已有的推理结果
#   适合：推理已完成，需要重新评分或使用不同评测方法
#
# -----------------------------------------------------------------------------
#
# 【场景4】多批次推理，分批评测
# -----------------------------------------------------------------------------
# 第一天跑第一批推理：
#   RUN_MODE="infer-only"
#   TARGETS=( "pt14_sf0:10052:ModelA:192.168.1.101" "pt15_sf0:10053:ModelA:192.168.1.102" )
#   bash multi_deploy_benchmark_v3.sh
#
# 第二天跑第二批推理：
#   修改 TARGETS 为 ModelB 的配置
#   bash multi_deploy_benchmark_v3.sh
#
# 统一评测所有推理结果：
#   RUN_MODE="judge-only"
#   INFER_TASK_ID="mixed_eval_"   # 会匹配所有以 mixed_eval_ 开头的任务
#   bash multi_deploy_benchmark_v3.sh
#
# ==============================================================================

set -euo pipefail

# ── 命令行参数解析（可覆盖配置区的值）────────────────────────────────
while [[ $# -gt 0 ]]; do
    case "$1" in
        --infer-task)
            INFER_TASK_ID="$2"
            shift 2
            ;;
        --eval-version)
            EVAL_VERSION="$2"
            shift 2
            ;;
        --run-mode)
            RUN_MODE="$2"
            shift 2
            ;;
        *)
            echo "❌ 未知参数: $1"
            echo "   支持: --infer-task <task_id>  --eval-version <version>  --run-mode <mode>"
            exit 1
            ;;
    esac
done

if [[ "$RUN_MODE" == "judge-only" ]] && [[ -z "$INFER_TASK_ID" ]]; then
    echo "⚠️  judge-only 模式未指定 INFER_TASK_ID，将自动选择各工作区 logs/ 下最新的推理任务"
fi

# ── 自动定位基础工作区 ──────────────────────────────────────────────────
if [ -z "$BASE_WORKSPACE" ]; then
    BASE_WORKSPACE=$(find "$DEPLOY_ROOT" -maxdepth 1 -type d -name "eval_workspace_*" | sort | tail -n 1)
    if [ -z "$BASE_WORKSPACE" ]; then
        echo "❌ 在 $DEPLOY_ROOT 下未找到 eval_workspace_* 目录"
        echo "   请先解压一份，或设置 BASE_WORKSPACE 变量指向已有目录"
        exit 1
    fi
fi

if [ ! -f "$BASE_WORKSPACE/.env" ]; then
    echo "❌ $BASE_WORKSPACE 不是有效的工作区（缺少 .env）"
    exit 1
fi

echo "📂 基础工作区: $BASE_WORKSPACE"
echo "📂 部署根目录: $DEPLOY_ROOT"

# 共享资源路径
SHARED_DATA="$BASE_WORKSPACE/data"
SHARED_CODE="$BASE_WORKSPACE/code"
BENCHMARK_SCRIPT="$BASE_WORKSPACE/run_mixed_benchmark.sh"
IMAGE_TAR="$BASE_WORKSPACE/benchmark-eval.tar.gz"

for res in "$SHARED_DATA" "$SHARED_CODE" "$BENCHMARK_SCRIPT"; do
    if [ ! -e "$res" ]; then
        echo "❌ 缺少共享资源: $res"
        exit 1
    fi
done

IMAGE_TAR_FLAG=()
if [ -f "$IMAGE_TAR" ]; then
    IMAGE_TAR_FLAG=(--image-tar "$IMAGE_TAR")
fi

# ── 结果记录文件 ──────────────────────────────────────────────────────────
BEIJING_DATE=$(TZ='Asia/Shanghai' date '+%Y%m%d')
RESULT_FILE="$DEPLOY_ROOT/model_eval_res_${BEIJING_DATE}.txt"

if [ ! -f "$RESULT_FILE" ]; then
    printf '%-19s | %-30s | %-8s | %-25s | %s\n' \
        "日期" "工作区" "端口" "模型名" "容器名称" \
        >> "$RESULT_FILE"
    printf '%s\n' "$(printf '%0.s-' {1..100})" >> "$RESULT_FILE"
fi

# ── 模式信息 ──────────────────────────────────────────────────────────────
case "$RUN_MODE" in
    infer)
        MODE_DESC="推理+评测模式"
        ;;
    infer-only)
        MODE_DESC="仅推理模式"
        ;;
    judge-only)
        MODE_DESC="仅评测模式"
        ;;
    *)
        echo "❌ 不支持的 RUN_MODE: $RUN_MODE（仅支持 infer、infer-only、judge-only）"
        exit 1
        ;;
esac
echo "📌 运行模式: $MODE_DESC"
[[ -n "$INFER_TASK_ID" ]] && echo "📌 推理任务前缀: $INFER_TASK_ID"

# ── 逐个目标部署 ──────────────────────────────────────────────────────────
for TARGET in "${TARGETS[@]}"; do
    IFS=':' read -r NAME PORT MODEL_NAME IP <<< "$TARGET"

    [ -z "$NAME" ] && echo "❌ TARGET 格式错误，缺少目录名: $TARGET" && continue
    [ -z "$PORT" ] && echo "❌ TARGET 格式错误，缺少端口: $TARGET" && continue

    : "${MODEL_NAME:=${DEFAULT_LOCAL_MODEL_NAME}}"
    : "${IP:=${DEFAULT_LOCAL_HOST_IP}}"

    WORKSPACE="$DEPLOY_ROOT/$NAME"

    echo "================================================="
    echo "🚀 部署: $NAME (端口: $PORT)"

    mkdir -p "$WORKSPACE/outputs" "$WORKSPACE/logs"

    if [ ! -e "$WORKSPACE/data" ]; then
        ln -s "$(cd "$SHARED_DATA" && pwd)" "$WORKSPACE/data"
        echo "🔗 data -> $SHARED_DATA"
    fi

    cp "$BASE_WORKSPACE/.env" "$WORKSPACE/.env"

    sed -i "s/^LOCAL_HOST_PORT=.*/LOCAL_HOST_PORT=${PORT}/g" "$WORKSPACE/.env"

    if [ -n "$IP" ]; then
        sed -i "s/^LOCAL_HOST_IP=.*/LOCAL_HOST_IP=${IP}/g" "$WORKSPACE/.env"
    fi

    if [ -n "$MODEL_NAME" ]; then
        sed -i "s/^LOCAL_MODEL_NAME=.*/LOCAL_MODEL_NAME=${MODEL_NAME}/g" "$WORKSPACE/.env"
    fi

    ENV_INFO="LOCAL_HOST_PORT=$PORT"
    [ -n "$IP" ] && ENV_INFO="$ENV_INFO, LOCAL_HOST_IP=$IP"
    [ -n "$MODEL_NAME" ] && ENV_INFO="$ENV_INFO, LOCAL_MODEL_NAME=$MODEL_NAME"
    echo "✅ .env: $ENV_INFO"

    if [ -f "$BENCHMARK_SCRIPT" ]; then
        BENCHMARK_ARGS=(
            --workspace "$WORKSPACE"
            --code-dir "$SHARED_CODE"
            "${IMAGE_TAR_FLAG[@]}"
        )

        case "$RUN_MODE" in
            infer-only)
                BENCHMARK_ARGS+=(--infer-only)
                ;;
            judge-only)
                BENCHMARK_ARGS+=(--judge-only)
                if [ -n "$INFER_TASK_ID" ]; then
                    BENCHMARK_ARGS+=(--infer-task "$INFER_TASK_ID")
                fi
                ;;
        esac

        if [ -n "$EVAL_VERSION" ]; then
            BENCHMARK_ARGS+=(--eval-version "$EVAL_VERSION")
        fi

        BENCHMARK_ARGS+=(--name "$NAME")

        bash "$BENCHMARK_SCRIPT" "${BENCHMARK_ARGS[@]}"

        case "$RUN_MODE" in
            infer-only) CONTAINER_NAMES="${NAME}-infer" ;;
            judge-only) CONTAINER_NAMES="${NAME}-judge" ;;
            infer)      CONTAINER_NAMES="${NAME}-all-infer / ${NAME}-all-judge" ;;
        esac
        echo "🐳 容器名称: $CONTAINER_NAMES"

        printf '%s | %-30s | %-8s | %-25s | %s\n' \
            "$BEIJING_DATE" "$NAME" "$PORT" "${MODEL_NAME:-N/A}" "$CONTAINER_NAMES" \
            >> "$RESULT_FILE"
    else
        echo "❌ 找不到启动脚本: $BENCHMARK_SCRIPT"
        printf '%s | %-30s | %-8s | %-25s | %s\n' \
            "$BEIJING_DATE" "$NAME" "$PORT" "${MODEL_NAME:-N/A}" "FAILED(no script)" \
            >> "$RESULT_FILE"
    fi

    echo "================================================="
    echo ""
done

echo "🎉 所有容器部署已触发完毕！"
echo "👉 查看日志: tail -f $DEPLOY_ROOT/<目标名>/logs/mixed_eval_*.log"
echo "📄 部署记录: $RESULT_FILE"