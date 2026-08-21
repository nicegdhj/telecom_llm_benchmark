import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data" / "custom_task"

# (task_id, 期望条数, 评估器, 系统提示词模式)
EXPECT = [
    (201, 774, "TelecomLLMJudgeEvaluator", "none"),
    (202, 175, "TelecomLLMJudgeEvaluator", "none"),
    (203, 300, "TelecomLLMJudgeEvaluator", "fold"),
    (204, 196, "TelecomLLMJudgeEvaluator", "none"),
    (205, 100, "TelecomLLMJudgeEvaluator", "none"),
    (206, 550, "TelecomLLMJudgeEvaluator", "system"),
    (207, 198, "TelecomLLMJudgeEvaluator", "none"),
    (208, 129, "TelecomLLMJudgeEvaluator", "none"),
    (209, 200, "JsonFieldEvaluator", "system"),
    (210, 1007, "JsonFieldEvaluator", "system"),
    (211, 46, "AccEvaluator", "fold"),
]


@pytest.mark.parametrize("task_id,n_expected,eval_type,prompt_mode", EXPECT)
def test_data_file(task_id, n_expected, eval_type, prompt_mode):
    p = DATA_DIR / f"task_{task_id}.jsonl"
    assert p.exists(), f"缺少 {p}"
    records = [
        json.loads(l)
        for l in p.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    assert len(records) == n_expected
    for rec in records:
        assert isinstance(rec["input"], str) and rec["input"].strip() != ""
        assert isinstance(rec["output"], str) and rec["output"].strip() != ""


@pytest.mark.parametrize("task_id,n_expected,eval_type,prompt_mode", EXPECT)
def test_no_lone_slash_input(task_id, n_expected, eval_type, prompt_mode):
    p = DATA_DIR / f"task_{task_id}.jsonl"
    records = [
        json.loads(l)
        for l in p.read_text(encoding="utf-8").splitlines()
        if l.strip()
    ]
    # input 不应是单个 "/"（避免把空提示词当成了问题）
    for rec in records:
        assert rec["input"].strip() != "/"
