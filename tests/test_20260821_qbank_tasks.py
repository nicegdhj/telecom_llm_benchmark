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


import importlib
import sys


@pytest.mark.parametrize("task_id,n_expected,eval_type,prompt_mode", EXPECT)
def test_suite_import(task_id, n_expected, eval_type, prompt_mode):
    sys.path.insert(0, str(ROOT))
    mod = importlib.import_module(
        f"ais_bench.benchmark.configs.datasets.custom_task.task_{task_id}_suite"
    )
    datasets = getattr(mod, f"task_{task_id}_datasets")
    assert len(datasets) == 1
    ds = datasets[0]
    assert ds["abbr"] == f"task_{task_id}"
    assert ds["path"] == f"data/custom_task/task_{task_id}.jsonl"
    assert ds["reader_cfg"]["input_columns"] == ["input"]
    assert ds["reader_cfg"]["output_column"] == "output"
    ev_cfg = ds["eval_cfg"]["evaluator"]
    assert ev_cfg["type"].__name__ == eval_type
    assert (getattr(mod, "SYSTEM_INSTRUCTION", None) is not None) == (prompt_mode == "system")
    if eval_type == "JsonFieldEvaluator":
        # 契约守卫：gold output 的每个顶层字段都必须在 field_config 中显式声明，
        # 否则 JsonFieldEvaluator 会以默认 exact/1.0 打分，strict_mode 下几乎全部判 0。
        gold_keys = set()
        for line in (DATA_DIR / f"task_{task_id}.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                rec = json.loads(line)
                gold_keys |= set(json.loads(rec["output"]).keys())
        assert gold_keys <= set(ev_cfg["field_config"].keys())
