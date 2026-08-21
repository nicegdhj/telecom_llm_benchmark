# OT-Full Evaluation Tasks Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 `data/ot-full` 下 8 个数据集新增 8 个可独立执行、可客观判分的 ais_bench 任务。

**Architecture:** 新增 `OTDataset` 将三种原始记录形态统一适配为 `input/output`，并提供 TeleLogs 标签后处理器。8 个 CLI 入口通过一个共享配置构造器生成标准 reader/infer/eval 配置，直接读取原始 JSONL，不复制数据。

**Tech Stack:** Python、Hugging Face `datasets.Dataset`、ais_bench Registry、mmengine Config、pytest。

---

## 文件结构

- Create: `ais_bench/benchmark/datasets/ot_full.py` — JSONL 加载、三种数据适配模式、TeleLogs 答案解析。
- Modify: `ais_bench/benchmark/datasets/__init__.py` — 导出并注册 `OTDataset`。
- Create: `ais_bench/benchmark/configs/datasets/ot_full/__init__.py` — 将目录声明为 Python 包。
- Create: `ais_bench/benchmark/configs/datasets/ot_full/_common.py` — 统一构造 reader、infer、eval 和 dataset 配置。
- Create: `ais_bench/benchmark/configs/datasets/ot_full/ot_3gpp_tsg.py`
- Create: `ais_bench/benchmark/configs/datasets/ot_full/ot_oranbench.py`
- Create: `ais_bench/benchmark/configs/datasets/ot_full/ot_sixg_bench.py`
- Create: `ais_bench/benchmark/configs/datasets/ot_full/ot_srsranbench.py`
- Create: `ais_bench/benchmark/configs/datasets/ot_full/ot_telelogs.py`
- Create: `ais_bench/benchmark/configs/datasets/ot_full/ot_telemath.py`
- Create: `ais_bench/benchmark/configs/datasets/ot_full/ot_teleqna.py`
- Create: `ais_bench/benchmark/configs/datasets/ot_full/ot_teletables.py`
- Create: `tests/UT/datasets/test_ot_full.py` — 数据适配与后处理器单元测试。
- Create: `tests/test_ot_full_tasks.py` — 真实数据计数和 8 个配置的集成测试。

## Task 1: OTDataset 数据适配器

**Files:**

- Create: `tests/UT/datasets/test_ot_full.py`
- Create: `ais_bench/benchmark/datasets/ot_full.py`
- Modify: `ais_bench/benchmark/datasets/__init__.py`

- [ ] **Step 1: 写数据适配器失败测试**

测试使用 `tmp_path` 写入最小 JSONL，覆盖：

```python
import json

import pytest

from ais_bench.benchmark.datasets.ot_full import OTDataset


def write_jsonl(path, records):
    path.write_text(
        "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records),
        encoding="utf-8",
    )


def test_mcq_converts_index_and_normalizes_matching_numeric_prefix(tmp_path):
    path = tmp_path / "test.jsonl"
    write_jsonl(path, [{
        "question": "Which one?",
        "choices": ["1. Alpha", "2. Beta", "3. Gamma", "4. Delta"],
        "answer": 1,
    }])

    dataset = OTDataset.load(str(path), mode="mcq")

    assert dataset[0]["input"] == (
        "Which one?\n\nA. Alpha\nB. Beta\nC. Gamma\nD. Delta"
    )
    assert dataset[0]["output"] == "B"


def test_mcq_supports_dynamic_choice_count(tmp_path):
    path = tmp_path / "test.jsonl"
    write_jsonl(path, [{
        "question": "Pick one",
        "choices": ["one", "two", "three", "four", "five"],
        "answer": 4,
    }])

    dataset = OTDataset.load(str(path), mode="mcq")

    assert dataset[0]["input"].endswith("E. five")
    assert dataset[0]["output"] == "E"


def test_json_label_builds_expected_object(tmp_path):
    path = tmp_path / "test.jsonl"
    write_jsonl(path, [{"question": "classify", "answer": "SA4"}])

    dataset = OTDataset.load(str(path), mode="json_label")

    assert json.loads(dataset[0]["output"]) == {"WORKING GROUP": "SA4"}


def test_plain_stringifies_numeric_answer(tmp_path):
    path = tmp_path / "test.jsonl"
    write_jsonl(path, [{"question": "calculate", "answer": 7.2e-5}])

    dataset = OTDataset.load(str(path), mode="plain")

    assert dataset[0] == {"input": "calculate", "output": "7.2e-05"}


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ({"answer": "A"}, "missing required field 'question'"),
        ({"question": "q", "choices": [], "answer": 0}, "at least 2 choices"),
        ({"question": "q", "choices": ["a", "b"], "answer": 2}, "out of range"),
    ],
)
def test_invalid_record_reports_file_and_line(tmp_path, record, message):
    path = tmp_path / "bad.jsonl"
    write_jsonl(path, [record])

    with pytest.raises(ValueError) as exc_info:
        OTDataset.load(str(path), mode="mcq")

    error = str(exc_info.value)
    assert str(path) in error
    assert "line 1" in error
    assert message in error


def test_unknown_mode_is_rejected(tmp_path):
    path = tmp_path / "test.jsonl"
    write_jsonl(path, [{"question": "q", "answer": "a"}])

    with pytest.raises(ValueError, match="unsupported OT dataset mode"):
        OTDataset.load(str(path), mode="unknown")
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
/opt/anaconda3/bin/python -m pytest tests/UT/datasets/test_ot_full.py -v
```

Expected: collection/import 失败，因为 `ais_bench.benchmark.datasets.ot_full` 尚不存在。

- [ ] **Step 3: 实现最小 OTDataset**

`ais_bench/benchmark/datasets/ot_full.py` 实现以下接口：

```python
import json
import re
import string
from pathlib import Path

from datasets import Dataset

from ais_bench.benchmark.datasets.base import BaseDataset
from ais_bench.benchmark.datasets.utils.datasets import get_data_path
from ais_bench.benchmark.registry import LOAD_DATASET


SUPPORTED_MODES = {"mcq", "json_label", "plain"}


def _error(path, line_number, message):
    raise ValueError(f"{path}: line {line_number}: {message}")


def _required(record, field, path, line_number):
    if field not in record:
        _error(path, line_number, f"missing required field '{field}'")
    return record[field]


def _normalize_choice_prefix(choice, position):
    return re.sub(
        rf"^\s*{position}[.)、]\s+",
        "",
        str(choice).strip(),
        count=1,
    )


def _adapt_mcq(record, path, line_number):
    question = _required(record, "question", path, line_number)
    choices = _required(record, "choices", path, line_number)
    answer = _required(record, "answer", path, line_number)
    if not isinstance(choices, list) or len(choices) < 2:
        _error(path, line_number, "mcq record must contain at least 2 choices")
    if len(choices) > len(string.ascii_uppercase):
        _error(path, line_number, "mcq record has more than 26 choices")
    if isinstance(answer, bool) or not isinstance(answer, int):
        _error(path, line_number, "mcq answer must be an integer index")
    if not 0 <= answer < len(choices):
        _error(path, line_number, "mcq answer index is out of range")

    option_lines = []
    for index, choice in enumerate(choices):
        letter = string.ascii_uppercase[index]
        text = _normalize_choice_prefix(choice, index + 1)
        option_lines.append(f"{letter}. {text}")
    return {
        "input": f"{str(question).strip()}\n\n" + "\n".join(option_lines),
        "output": string.ascii_uppercase[answer],
    }


def _adapt_record(record, mode, path, line_number):
    question = _required(record, "question", path, line_number)
    if mode == "mcq":
        return _adapt_mcq(record, path, line_number)
    answer = _required(record, "answer", path, line_number)
    if mode == "json_label":
        output = json.dumps(
            {"WORKING GROUP": str(answer).strip()},
            ensure_ascii=False,
        )
    else:
        output = str(answer).strip()
    return {"input": str(question).strip(), "output": output}


@LOAD_DATASET.register_module()
class OTDataset(BaseDataset):

    @staticmethod
    def load(path, mode, **kwargs):
        if mode not in SUPPORTED_MODES:
            raise ValueError(f"unsupported OT dataset mode: {mode}")
        resolved_path = Path(get_data_path(path, local_mode=True))
        records = []
        with resolved_path.open("r", encoding="utf-8-sig") as source:
            for line_number, line in enumerate(source, start=1):
                if not line.strip():
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError as exc:
                    _error(resolved_path, line_number, f"invalid JSON: {exc.msg}")
                if not isinstance(record, dict):
                    _error(resolved_path, line_number, "record must be a JSON object")
                records.append(
                    _adapt_record(record, mode, resolved_path, line_number)
                )
        return Dataset.from_list(records)
```

在 `ais_bench/benchmark/datasets/__init__.py` 末尾追加：

```python
from ais_bench.benchmark.datasets.ot_full import *  # noqa: F401, F403
```

- [ ] **Step 4: 运行测试并确认 GREEN**

Run:

```bash
/opt/anaconda3/bin/python -m pytest tests/UT/datasets/test_ot_full.py -v
```

Expected: 当前数据适配测试全部 PASS。

## Task 2: TeleLogs 答案后处理器

**Files:**

- Modify: `tests/UT/datasets/test_ot_full.py`
- Modify: `ais_bench/benchmark/datasets/ot_full.py`

- [ ] **Step 1: 写 TeleLogs 解析失败测试**

追加：

```python
from ais_bench.benchmark.datasets.ot_full import telelogs_postprocess


@pytest.mark.parametrize(
    ("prediction", "expected"),
    [
        ("C1", "C1"),
        (r"\boxed{C2}", "C2"),
        (r"The final answer is \boxed{3}.", "C3"),
        ("分析完成。\n答案：C8", "C8"),
    ],
)
def test_telelogs_postprocess_accepts_supported_forms(prediction, expected):
    assert telelogs_postprocess(prediction) == expected


@pytest.mark.parametrize("prediction", ["", "C9", "C1 or C2", r"\boxed{0}"])
def test_telelogs_postprocess_rejects_invalid_or_ambiguous_answers(prediction):
    assert telelogs_postprocess(prediction) == ""
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
/opt/anaconda3/bin/python -m pytest tests/UT/datasets/test_ot_full.py -v
```

Expected: import 失败，因为 `telelogs_postprocess` 尚不存在。

- [ ] **Step 3: 实现并注册后处理器**

在 `ot_full.py` 中导入 `TEXT_POSTPROCESSORS`，并实现：

```python
from ais_bench.benchmark.registry import LOAD_DATASET, TEXT_POSTPROCESSORS


@TEXT_POSTPROCESSORS.register_module("telelogs_postprocess")
def telelogs_postprocess(text):
    candidates = []
    patterns = [
        r"\\boxed\s*\{\s*C?([1-8])\s*\}",
        r"(?:答案|answer)\s*[:：]?\s*C?([1-8])\b",
        r"(?<![A-Za-z0-9])C([1-8])(?![A-Za-z0-9])",
    ]
    for pattern in patterns:
        candidates.extend(re.findall(pattern, str(text), flags=re.IGNORECASE))
    unique = set(candidates)
    if len(unique) != 1:
        return ""
    return f"C{unique.pop()}"
```

- [ ] **Step 4: 运行测试并确认 GREEN**

Run:

```bash
/opt/anaconda3/bin/python -m pytest tests/UT/datasets/test_ot_full.py -v
```

Expected: 全部 PASS。

## Task 3: 共享配置构造器与 8 个任务入口

**Files:**

- Create: `ais_bench/benchmark/configs/datasets/ot_full/__init__.py`
- Create: `ais_bench/benchmark/configs/datasets/ot_full/_common.py`
- Create: 8 个 `ot_*.py` 任务文件
- Create: `tests/test_ot_full_tasks.py`

- [ ] **Step 1: 写真实数据和配置失败测试**

`tests/test_ot_full_tasks.py`：

```python
from pathlib import Path

import pytest
from mmengine.config import Config

from ais_bench.benchmark.datasets.ot_full import OTDataset


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
    assert dataset_cfg["eval_cfg"]["evaluator"]["type"].__name__ == evaluator_name
```

- [ ] **Step 2: 运行测试并确认 RED**

Run:

```bash
/opt/anaconda3/bin/python -m pytest tests/test_ot_full_tasks.py -v
```

Expected: 配置文件不存在，测试失败。

- [ ] **Step 3: 实现共享配置构造器**

`ais_bench/benchmark/configs/datasets/ot_full/_common.py` 提供：

```python
from ais_bench.benchmark.datasets import OTDataset
from ais_bench.benchmark.openicl.icl_evaluator import (
    AccEvaluator,
    JsonFieldEvaluator,
    MATHEvaluator,
)
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.utils.postprocess.text_postprocessors import (
    first_option_postprocess,
)
from ais_bench.benchmark.datasets.ot_full import telelogs_postprocess


MCQ_PROMPT = (
    "{input}\n\nSelect the correct answer and output only one option letter "
    "from A to E.\nAnswer:"
)
TELEMATH_PROMPT = (
    "{input}\nPlease reason step by step, and put your final answer "
    "within \\boxed{}."
)


def _infer_cfg(prompt):
    return dict(
        prompt_template=dict(type=PromptTemplate, template=prompt),
        retriever=dict(type=ZeroRetriever),
        inferencer=dict(type=GenInferencer),
    )


def build_ot_dataset(abbr, directory, mode, evaluator):
    if evaluator == "mcq":
        infer_cfg = _infer_cfg(MCQ_PROMPT)
        eval_cfg = dict(
            evaluator=dict(type=AccEvaluator),
            pred_postprocessor=dict(
                type=first_option_postprocess,
                options="ABCDE",
            ),
        )
    elif evaluator == "json_label":
        infer_cfg = _infer_cfg("{input}")
        eval_cfg = dict(
            evaluator=dict(
                type=JsonFieldEvaluator,
                field_config={
                    "WORKING GROUP": {"match_type": "exact", "weight": 1.0},
                },
                default_match_type="exact",
                return_details=True,
                strict_mode=True,
            )
        )
    elif evaluator == "telelogs":
        infer_cfg = _infer_cfg("{input}")
        eval_cfg = dict(
            evaluator=dict(type=AccEvaluator),
            pred_postprocessor=dict(type=telelogs_postprocess),
        )
    elif evaluator == "math":
        infer_cfg = _infer_cfg(TELEMATH_PROMPT)
        eval_cfg = dict(evaluator=dict(type=MATHEvaluator))
    else:
        raise ValueError(f"unsupported OT evaluator: {evaluator}")

    return [
        dict(
            type=OTDataset,
            abbr=abbr,
            path=(
                f"data/ot-full/{directory}/test-00000-of-00001.jsonl"
            ),
            mode=mode,
            reader_cfg=dict(input_columns=["input"], output_column="output"),
            infer_cfg=infer_cfg,
            eval_cfg=eval_cfg,
        )
    ]
```

`__init__.py` 为空文件。

- [ ] **Step 4: 创建 8 个任务入口**

每个文件只导入构造器并定义唯一的 `*_datasets`：

```python
# ot_3gpp_tsg.py
from ais_bench.benchmark.configs.datasets.ot_full._common import build_ot_dataset
ot_3gpp_tsg_datasets = build_ot_dataset(
    "ot_3gpp_tsg", "3gpp_tsg", "json_label", "json_label"
)

# ot_oranbench.py
from ais_bench.benchmark.configs.datasets.ot_full._common import build_ot_dataset
ot_oranbench_datasets = build_ot_dataset(
    "ot_oranbench", "oranbench", "mcq", "mcq"
)

# ot_sixg_bench.py
from ais_bench.benchmark.configs.datasets.ot_full._common import build_ot_dataset
ot_sixg_bench_datasets = build_ot_dataset(
    "ot_sixg_bench", "sixg_bench", "mcq", "mcq"
)

# ot_srsranbench.py
from ais_bench.benchmark.configs.datasets.ot_full._common import build_ot_dataset
ot_srsranbench_datasets = build_ot_dataset(
    "ot_srsranbench", "srsranbench", "mcq", "mcq"
)

# ot_telelogs.py
from ais_bench.benchmark.configs.datasets.ot_full._common import build_ot_dataset
ot_telelogs_datasets = build_ot_dataset(
    "ot_telelogs", "telelogs", "plain", "telelogs"
)

# ot_telemath.py
from ais_bench.benchmark.configs.datasets.ot_full._common import build_ot_dataset
ot_telemath_datasets = build_ot_dataset(
    "ot_telemath", "telemath", "plain", "math"
)

# ot_teleqna.py
from ais_bench.benchmark.configs.datasets.ot_full._common import build_ot_dataset
ot_teleqna_datasets = build_ot_dataset(
    "ot_teleqna", "teleqna", "mcq", "mcq"
)

# ot_teletables.py
from ais_bench.benchmark.configs.datasets.ot_full._common import build_ot_dataset
ot_teletables_datasets = build_ot_dataset(
    "ot_teletables", "teletables", "mcq", "mcq"
)
```

- [ ] **Step 5: 运行配置测试并确认 GREEN**

Run:

```bash
/opt/anaconda3/bin/python -m pytest tests/test_ot_full_tasks.py -v
```

Expected: 16 个参数化用例全部 PASS。

## Task 4: CLI 发现与回归验证

**Files:**

- Verify only; no expected production changes.

- [ ] **Step 1: 运行全部新增测试**

Run:

```bash
/opt/anaconda3/bin/python -m pytest \
  tests/UT/datasets/test_ot_full.py \
  tests/test_ot_full_tasks.py -v
```

Expected: 全部 PASS，无 error。

- [ ] **Step 2: 验证 8 个任务可被 CLI 配置管理器发现**

Run:

```bash
/opt/anaconda3/bin/python -c '
from pathlib import Path
from ais_bench.benchmark.utils.file.file import match_cfg_file
root = Path("ais_bench/benchmark/configs/datasets")
names = [
    "ot_3gpp_tsg", "ot_oranbench", "ot_sixg_bench", "ot_srsranbench",
    "ot_telelogs", "ot_telemath", "ot_teleqna", "ot_teletables",
]
for name in names:
    matches = match_cfg_file(str(root), [name])
    assert len(matches) == 1, (name, matches)
    print(name, matches[0][1])
'
```

Expected: 输出 8 行，每个任务恰好匹配一个配置文件。

- [ ] **Step 3: 验证数据配置可构建**

Run:

```bash
/opt/anaconda3/bin/python -c '
from mmengine.config import Config
from ais_bench.benchmark.utils.config.build import build_dataset_from_cfg
names = [
    "ot_3gpp_tsg", "ot_oranbench", "ot_sixg_bench", "ot_srsranbench",
    "ot_telelogs", "ot_telemath", "ot_teleqna", "ot_teletables",
]
for name in names:
    cfg = Config.fromfile(
        f"ais_bench/benchmark/configs/datasets/ot_full/{name}.py"
    )
    datasets = next(value for key, value in cfg.items() if key.endswith("_datasets"))
    dataset = build_dataset_from_cfg(datasets[0])
    print(name, len(dataset))
'
```

Expected: 输出 8 个任务及其设计条数：2000、1500、3722、1502、864、500、10000、500。

- [ ] **Step 4: 运行相邻数据集回归测试**

Run:

```bash
/opt/anaconda3/bin/python -m pytest tests/UT/datasets -q
```

Expected: 测试通过；若存在与本次无关的既有失败，只记录，不修改无关代码。

- [ ] **Step 5: 检查补丁格式和范围**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` 无输出；本次新增或修改仅涉及设计/计划、OT 数据适配器、OT 配置和对应测试。工作区内原有其他修改保持不变。

## 交付说明

本计划不包含 Git 提交步骤；只有用户明确要求提交时才执行 commit。实现完成后提供 8 个任务的执行命令及测试结果。
