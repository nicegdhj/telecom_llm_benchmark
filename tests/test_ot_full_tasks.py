from pathlib import Path

import pytest
from mmengine.config import Config

from ais_bench.benchmark.datasets.ot_full import OTDataset, telelogs_postprocess


ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = ROOT / "ais_bench/benchmark/configs/datasets/ot_full"

TASKS = [
    ("ot_3gpp_tsg", "3gpp_tsg", "json_label", 2000, "JsonFieldEvaluator"),
    ("ot_oranbench", "oranbench", "mcq", 1500, "AccEvaluator"),
    ("ot_sixg_bench", "sixg_bench", "mcq", 3722, "AccEvaluator"),
    ("ot_srsranbench", "srsranbench", "mcq", 1502, "AccEvaluator"),
    ("ot_telelogs", "telelogs", "plain", 864, "AccEvaluator"),
    ("ot_telemath", "telemath", "plain", 500, "MATHEvaluator"),
    ("ot_teleqna", "teleqna", "mcq", 10000, "AccEvaluator"),
    ("ot_teletables", "teletables", "mcq", 500, "AccEvaluator"),
]


@pytest.mark.parametrize(
    ("task_name", "directory", "mode", "expected_count", "evaluator_name"),
    TASKS,
)
def test_real_ot_dataset_count(
    task_name, directory, mode, expected_count, evaluator_name
):
    path = ROOT / "data/ot-full" / directory / "test-00000-of-00001.jsonl"

    dataset = OTDataset.load(str(path), mode=mode)

    assert len(dataset) == expected_count
    assert all(item["input"] and item["output"] for item in dataset)


@pytest.mark.parametrize(
    ("task_name", "directory", "mode", "expected_count", "evaluator_name"),
    TASKS,
)
def test_ot_task_config(
    task_name, directory, mode, expected_count, evaluator_name
):
    cfg = Config.fromfile(CONFIG_DIR / f"{task_name}.py")
    dataset_lists = [value for key, value in cfg.items() if key.endswith("_datasets")]

    assert len(dataset_lists) == 1
    dataset_cfg = dataset_lists[0][0]
    assert dataset_cfg["abbr"] == task_name
    assert dataset_cfg["mode"] == mode
    assert dataset_cfg["path"] == (
        f"data/ot-full/{directory}/test-00000-of-00001.jsonl"
    )
    assert dataset_cfg["eval_cfg"]["evaluator"]["type"].split(".")[-1] == (
        evaluator_name
    )


@pytest.mark.parametrize(
    "task_name",
    [task_name for task_name, *_ in TASKS],
)
def test_ot_task_config_survives_cli_dump_and_reload(tmp_path, task_name):
    cfg = Config.fromfile(CONFIG_DIR / f"{task_name}.py")
    merged_cfg = Config(
        dict(datasets=getattr(cfg, f"{task_name}_datasets"))
    )
    dumped_path = tmp_path / f"{task_name}.py"

    merged_cfg.dump(dumped_path)
    reloaded_cfg = Config.fromfile(dumped_path, format_python_code=False)

    assert reloaded_cfg.datasets[0]["abbr"] == task_name


@pytest.mark.parametrize(
    "task_name",
    [
        "ot_oranbench",
        "ot_sixg_bench",
        "ot_srsranbench",
        "ot_teleqna",
        "ot_teletables",
    ],
)
def test_mcq_config_prompt_and_postprocessor(task_name):
    cfg = Config.fromfile(CONFIG_DIR / f"{task_name}.py")
    dataset_cfg = getattr(cfg, f"{task_name}_datasets")[0]

    assert dataset_cfg["infer_cfg"]["prompt_template"]["template"] == (
        "{input}\n\nSelect the correct answer and output only one option letter "
        "from A to E.\nAnswer:"
    )
    assert dataset_cfg["eval_cfg"]["pred_postprocessor"]["type"] == (
        "ais_bench.benchmark.utils.postprocess.text_postprocessors."
        "first_option_postprocess"
    )
    assert dataset_cfg["eval_cfg"]["pred_postprocessor"]["options"] == "ABCDE"


def test_3gpp_config_uses_strict_working_group_match():
    cfg = Config.fromfile(CONFIG_DIR / "ot_3gpp_tsg.py")
    evaluator_cfg = cfg.ot_3gpp_tsg_datasets[0]["eval_cfg"]["evaluator"]

    assert evaluator_cfg["field_config"] == {
        "WORKING GROUP": {"match_type": "exact", "weight": 1.0},
    }
    assert evaluator_cfg["strict_mode"] is True


def test_telelogs_config_wires_telelogs_postprocessor():
    cfg = Config.fromfile(CONFIG_DIR / "ot_telelogs.py")
    postprocessor_cfg = cfg.ot_telelogs_datasets[0]["eval_cfg"][
        "pred_postprocessor"
    ]

    assert postprocessor_cfg["type"] == (
        "ais_bench.benchmark.datasets.ot_full.telelogs_postprocess"
    )


def test_telemath_config_uses_literal_boxed_answer_prompt():
    cfg = Config.fromfile(CONFIG_DIR / "ot_telemath.py")

    assert cfg.ot_telemath_datasets[0]["infer_cfg"]["prompt_template"][
        "template"
    ] == (
        "{input}\nPlease reason step by step, and put your final answer "
        "within \\boxed{}."
    )


@pytest.mark.parametrize(
    ("prediction", "expected"),
    [
        # JSON 预测：只从 root_cause 字段提取 C 标签，忽略推理文本中的其他 C 引用
        ('{"analysis_summary": "...", "root_cause": "C4", "reasoning": "..."}', "C4"),
        # root_cause 带描述
        (
            '{"analysis_summary": "...", "root_cause": "C2: Non-colocated co-frequency.", "reasoning": "..."}',
            "C2",
        ),
        # 兼容 root_case 别名
        ('{"analysis_summary": "...", "root_case": "C7", "reasoning": "..."}', "C7"),
        # JSON 但无 root_cause/root_case → 回退全文本正则
        ('{"analysis_summary": "mentions C1 and C5", "reasoning": "C2"}', ""),
        # 非 JSON → 回退全文本正则
        ("The answer is \\boxed{C5}", "C5"),
        ("answer: C3", "C3"),
        ("C1 C2 C3 are all possible", ""),
        ("plain text without any root cause", ""),
    ],
)
def test_telelogs_postprocess_root_cause_extraction(prediction, expected):
    assert telelogs_postprocess(prediction) == expected


@pytest.mark.parametrize(
    ("prediction", "expected"),
    [
        # root_cause 有多个不同 C 标签 → 判定为歧义，返回空
        ('{"root_cause": "C1", "root_cause_alt": "C2", "reasoning": "..."}', "C1"),
        # root_cause 值里出现多个不同 C 标签 → 返回空
        ('{"analysis_summary": "...", "root_cause": "C1, C2 both possible"}', ""),
    ],
)
def test_telelogs_postprocess_root_cause_ambiguity(prediction, expected):
    assert telelogs_postprocess(prediction) == expected
