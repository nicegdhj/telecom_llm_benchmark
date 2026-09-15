"""框架日志错误检测：框架内部捕获异常仍 exit 0 时，需据日志判失败。

仅匹配框架自报信号，避免命中被原样回显的模型输出内容。
"""
from backend.app.services.framework_log import (
    detect_framework_error, eval_log_files, infer_log_files,
)


def _out(tmp_path, name, text):
    f = tmp_path / name
    f.write_text(text, encoding="utf-8")
    return [f]


def test_detect_traceback(tmp_path):
    log = (
        "[2026-05-20 10:01:28] [ais_bench] [INFO] Apply ice template finished\n"
        "Traceback (most recent call last):\n"
        '  File "openicl_api_infer.py", line 775, in <module>\n'
        "    raise e\n"
        "ValueError: Column 'reference' doesn't exist.\n"
    )
    err = detect_framework_error(_out(tmp_path, "task.out", log))
    assert err is not None
    assert "Column 'reference'" in err


def test_detect_task_state_error(tmp_path):
    log = "[ais_bench] [WARNING] Task state is error, exit loop\n"
    err = detect_framework_error(_out(tmp_path, "task.out", log))
    assert err is not None
    assert "error" in err


def test_clean_log_no_error(tmp_path):
    log = (
        "[ais_bench] [INFO] Task finished, failed reasons summary:\n"
        "| Too Many Requests | 170 |\n"
        "[ais_bench] [INFO] Task state is finish, exit loop\n"
    )
    assert detect_framework_error(_out(tmp_path, "task.out", log)) is None


def test_model_output_with_traceback_word_not_flagged(tmp_path):
    # 模型输出被原样回显在单行 INFO 内，其中含 "Traceback" 字样不应误判
    log = (
        "[ais_bench] [INFO]   Output: '让我想想，报错信息是 Traceback (most recent "
        "call last): 这种格式，但这只是模型在解释概念'\n"
        "[ais_bench] [INFO] Task state is finish, exit loop\n"
    )
    assert detect_framework_error(_out(tmp_path, "task.out", log)) is None


def test_no_files():
    assert detect_framework_error([]) is None


def _touch(p):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("log", encoding="utf-8")


def test_infer_log_final_location(tmp_path):
    otid = "batchX"
    f = tmp_path / "outputs" / otid / "details" / "20260101_000000" / "logs" / "infer" / "common_gateway" / "task_1.out"
    _touch(f)
    assert infer_log_files(tmp_path, otid) == [f]


def test_infer_log_live_fallback(tmp_path):
    # 运行中：details 还没有，日志在 outputs/default/
    otid = "batchX"
    live = tmp_path / "outputs" / "default" / "20260101_000000" / "logs" / "infer" / "common_gateway" / "task_1.out"
    _touch(live)
    assert infer_log_files(tmp_path, otid) == [live]


def test_eval_log_final_location(tmp_path):
    otid = "batchX"
    f = tmp_path / "outputs" / otid / "eval_init" / "logs" / "task_1_suite" / "task_1.out"
    _touch(f)
    assert eval_log_files(tmp_path, otid, "eval_init") == [f]


def test_eval_log_live_fallback(tmp_path):
    # 运行中：eval 日志在 details/<ts>/logs/eval/
    otid = "batchX"
    live = tmp_path / "outputs" / otid / "details" / "20260101_000000" / "logs" / "eval" / "common_gateway" / "task_1.out"
    _touch(live)
    assert eval_log_files(tmp_path, otid, "eval_init") == [live]
