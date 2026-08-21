#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STATE_DIR="$SCRIPT_DIR/.runs"
PID_FILE="$STATE_DIR/active.pid"
LOG_PATH_FILE="$STATE_DIR/active.log"
START_TIME_FILE="$STATE_DIR/active.start_time"
START_LOCK_DIR="$STATE_DIR/start.lock"
PYTHON_BIN="${PYTHON_BIN:-python3}"
CONFIG_FILE="${MINI_DEMO_CONFIG:-$SCRIPT_DIR/config.env}"

load_config() {
    [[ -f "$CONFIG_FILE" ]] || return
    local variable index
    local preserved_names=()
    local preserved_values=()
    local variables=(
        INFER_API_KEY
        INFER_BASE_URL
        INFER_MODEL
        DEEPSEEK_V4_FLASH_INFER_API_KEY
        DEEPSEEK_V4_FLASH_INFER_BASE_URL
        JUDGE_API_KEY
        JUDGE_BASE_URL
        JUDGE_MODEL
    )
    for variable in "${variables[@]}"; do
        if printenv "$variable" >/dev/null 2>&1; then
            preserved_names+=("$variable")
            preserved_values+=("${!variable}")
        fi
    done
    set -a
    source "$CONFIG_FILE"
    set +a
    for ((index = 0; index < ${#preserved_names[@]}; index++)); do
        export "${preserved_names[$index]}=${preserved_values[$index]}"
    done
}

load_config

mkdir -p "$STATE_DIR" "$SCRIPT_DIR/outputs"

is_running() {
    [[ -f "$PID_FILE" ]] || return 1
    [[ -f "$START_TIME_FILE" ]] || return 1
    local pid process_command expected_start_time actual_start_time
    pid="$(cat "$PID_FILE")"
    [[ "$pid" =~ ^[0-9]+$ ]] || return 1
    kill -0 "$pid" 2>/dev/null || return 1
    expected_start_time="$(cat "$START_TIME_FILE")"
    actual_start_time="$(ps -p "$pid" -o lstart= 2>/dev/null || true)"
    [[ -n "$actual_start_time" && "$actual_start_time" == "$expected_start_time" ]] || return 1
    process_command="$(ps -p "$pid" -o command= 2>/dev/null || true)"
    [[ "$process_command" == *"$SCRIPT_DIR/mini_eval.py"* ]]
}

start() {
    if ! mkdir "$START_LOCK_DIR" 2>/dev/null; then
        echo "另一个启动操作正在进行中"
        exit 1
    fi
    trap 'rmdir "$START_LOCK_DIR" 2>/dev/null || true' EXIT
    if is_running; then
        echo "已有任务运行中，PID=$(cat "$PID_FILE")"
        exit 1
    fi
    local launch_id log_path pid start_time
    launch_id="$(date '+%Y%m%d_%H%M%S')_$$"
    log_path="$STATE_DIR/$launch_id.log"
    nohup "$PYTHON_BIN" "$SCRIPT_DIR/mini_eval.py" \
        --output-dir "$SCRIPT_DIR/outputs" "$@" \
        >"$log_path" 2>&1 &
    pid=$!
    printf '%s\n' "$pid" >"$PID_FILE"
    printf '%s\n' "$log_path" >"$LOG_PATH_FILE"
    start_time="$(ps -p "$pid" -o lstart= 2>/dev/null || true)"
    if [[ -z "$start_time" ]]; then
        echo "任务启动失败，日志：$log_path"
        cat "$log_path"
        rm -f "$PID_FILE" "$START_TIME_FILE"
        exit 1
    fi
    printf '%s\n' "$start_time" >"$START_TIME_FILE"
    sleep 0.2
    if ! is_running; then
        echo "任务启动失败，日志：$log_path"
        cat "$log_path"
        rm -f "$PID_FILE" "$START_TIME_FILE"
        exit 1
    fi
    rmdir "$START_LOCK_DIR"
    trap - EXIT
    echo "任务已启动，PID=$pid"
    echo "日志：$log_path"
}

status() {
    if is_running; then
        echo "任务运行中，PID=$(cat "$PID_FILE")"
    elif [[ -f "$PID_FILE" ]]; then
        echo "任务已结束，PID=$(cat "$PID_FILE")"
    else
        echo "当前没有活动任务"
    fi
}

logs() {
    if [[ ! -f "$LOG_PATH_FILE" ]]; then
        echo "暂无任务日志"
        exit 1
    fi
    tail -f "$(cat "$LOG_PATH_FILE")"
}

stop() {
    if ! is_running; then
        echo "当前没有运行中的任务"
        rm -f "$PID_FILE" "$START_TIME_FILE"
        return
    fi
    local pid
    pid="$(cat "$PID_FILE")"
    kill "$pid"
    for _ in {1..25}; do
        if ! is_running; then
            rm -f "$PID_FILE" "$START_TIME_FILE"
            echo "任务已停止，PID=$pid"
            return
        fi
        sleep 0.2
    done
    echo "任务仍在退出中，PID=$pid"
}

usage() {
    echo "用法: $0 {start|status|logs|stop} [mini_eval.py 参数]"
}

command="${1:-}"
if [[ -n "$command" ]]; then
    shift
fi
case "$command" in
    start) start "$@" ;;
    status) status ;;
    logs) logs ;;
    stop) stop ;;
    *) usage; exit 1 ;;
esac
