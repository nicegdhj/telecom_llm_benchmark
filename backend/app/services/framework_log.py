"""ais_bench 框架日志的定位与错误检测。

框架（容器内 ais_bench）在某些错误下会内部捕获异常、把 traceback 打进 .out 日志，
却仍以退出码 0 结束 → 任务被误判为 success。本模块提供：
- 定位 infer / eval 的框架 .out 日志文件
- 从日志中检测"框架级错误"（仅匹配框架自报信号，避免命中被原样回显的模型输出内容）
"""
import re
from pathlib import Path

# 框架级错误的可靠标记：
# - 物理行顶格的 Python traceback（模型输出是单行 repr，其内的 "Traceback" 不会顶格成行）
# - ais_bench 显式把任务置为 error 状态
_TRACEBACK = re.compile(r"^Traceback \(most recent call last\):", re.MULTILINE)
_TASK_ERROR = re.compile(r"Task state is error")
# traceback 末尾的异常行，如 "ValueError: Column 'reference' doesn't exist."
_EXC_LINE = re.compile(r"^\s*\w[\w.]*(?:Error|Exception|Warning|Interrupt):.*$", re.MULTILINE)


def _outs(base: Path) -> list[Path]:
    return sorted(base.glob("**/*.out")) + sorted(base.glob("**/*.log"))


def infer_log_files(workspace_dir: Path, output_task_id: str) -> list[Path]:
    """infer 框架日志。完成后在 details/ 下；运行中 ais_bench 还在写 outputs/default/。"""
    outputs = Path(workspace_dir) / "outputs"
    base = outputs / output_task_id / "details"
    files = (sorted(base.glob("**/logs/infer/**/*.out"))
             + sorted(base.glob("**/logs/infer/**/*.log")))
    if not files:  # 运行中：日志尚未搬运，落在 outputs/default/<ts>/logs/infer/
        live = outputs / "default"
        files = (sorted(live.glob("**/logs/infer/**/*.out"))
                 + sorted(live.glob("**/logs/infer/**/*.log")))
    return files


def eval_log_files(workspace_dir: Path, output_task_id: str,
                   eval_version: str) -> list[Path]:
    """eval 框架日志。完成后在 <eval_version>/logs/ 下；运行中在 details/<ts>/logs/eval/。"""
    outputs = Path(workspace_dir) / "outputs"
    files = _outs(outputs / output_task_id / eval_version / "logs")
    if not files:  # 运行中：日志尚未搬运，落在 details/<ts>/logs/eval/
        base = outputs / output_task_id / "details"
        files = (sorted(base.glob("**/logs/eval/**/*.out"))
                 + sorted(base.glob("**/logs/eval/**/*.log")))
    return files


def detect_framework_error(files: list[Path]) -> str | None:
    """扫描框架日志文件，命中错误时返回简短摘要，否则 None。"""
    for f in files:
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if _TRACEBACK.search(text):
            exc = _EXC_LINE.search(text)
            summary = exc.group(0).strip() if exc else "框架抛出未捕获异常 (Traceback)"
            return f"{f.name}: {summary[:300]}"
        if _TASK_ERROR.search(text):
            return f"{f.name}: 框架任务状态为 error"
    return None
