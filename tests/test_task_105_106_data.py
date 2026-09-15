import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.prepare_task_105_106 import build_task_records


def test_task_105_keeps_each_cumulative_turn_with_session_metadata():
    rows = [
        {"session_id": "a", "input": "第一轮", "业务类别": "工单派发", "宽带账号": "abc"},
        {"session_id": "a", "input": "第二轮", "业务类别": "暂不确定", "宽带账号": ""},
        {"session_id": "b", "input": "另一段", "业务类别": "不支持该业务", "宽带账号": "xyz"},
    ]

    task_105, task_106 = build_task_records(rows)

    assert len(task_105) == 3
    assert task_105[0]["input"] == "用户：第一轮"
    assert task_105[1]["input"] == "用户：第一轮\n用户：第二轮"
    assert task_105[1]["session_id"] == "a"
    assert task_105[1]["turn_index"] == 2
    assert task_105[1]["turn_count"] == 2
    assert json.loads(task_105[0]["output"]) == {
        "业务类别": "工单派发",
        "信息提取": {"宽带账号": "abc"},
    }
    assert task_106[1]["input"] == "用户：第一轮\n用户：第二轮"
    assert json.loads(task_106[1]["output"]) == {
        "业务类别": "暂不确定",
        "信息提取": {},
    }


def test_task_records_keep_nonempty_extraction_fields_only():
    rows = [{
        "session_id": "a",
        "input": "查询",
        "业务类别": "查询宽带账号",
        "宽带账号": "abc123",
        "手机号": "",
        "密码": None,
    }]

    task_105, _ = build_task_records(rows)

    assert json.loads(task_105[0]["output"]) == {
        "业务类别": "查询宽带账号",
        "信息提取": {"宽带账号": "abc123"},
    }


def test_interleaved_session_rows_are_recombined_by_session_id():
    rows = [
        {"session_id": "1", "input": "1-1", "业务类别": "A"},
        {"session_id": "2", "input": "2-1", "业务类别": "B"},
        {"session_id": "1", "input": "1-2", "业务类别": "C"},
    ]

    task_105, task_106 = build_task_records(rows)

    assert task_105[0]["input"] == "用户：1-1"
    assert task_105[1]["input"] == "用户：1-1\n用户：1-2"
    assert json.loads(task_105[1]["output"])["业务类别"] == "C"
    assert task_105[1]["session_id"] == "1"
    assert len(task_106) == 3
