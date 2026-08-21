# 20260821 专业题库评测任务构建实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `mydata/20260821专业题库测试` 下的 11 个专业题库 xlsx 构建为 11 个评测任务（jsonl 数据集 + suite 评估算子 + 映射文档）。

**Architecture:** 单一构建脚本 `scripts/build_20260821_qbank_tasks.py` 按任务清单读取 xlsx → 生成 `data/custom_task/task_2NN.jsonl` 与 `ais_bench/benchmark/configs/datasets/custom_task/task_2NN_suite.py` → 生成映射文档 `docs/20260821专业题库任务映射.md`。测试用 pytest 验证数据条数/结构 + suite 可导入/评估器正确。

**Tech Stack:** Python（base env `/opt/anaconda3/bin/python`，含 openpyxl 3.1.5、pytest 8.3.4、ais_bench）、openpyxl、jsonl。

## Global Constraints

- 数据集一律 `{"input", "output"}` 每行一条，UTF-8 编码。
- 输出文件路径：`data/custom_task/task_2NN.jsonl` 与 `ais_bench/benchmark/configs/datasets/custom_task/task_2NN_suite.py`。
- 任务编号固定：201–208 = 各专业知识理解；209–211 = 各专业意图识别（已确认）。
- 评估器固定：知识理解 → `TelecomLLMJudgeEvaluator`；个人业务/核心网意图识别 → `JsonFieldEvaluator`；监控意图识别 → `AccEvaluator`（已确认）。
- 提示词规则（基于源数据核查后的细化，覆盖原 spec 的"有提示词硬编码为 SYSTEM_INSTRUCTION"）：
  - 提示词**恒定**（task_206、task_209、task_210）→ 取列众数作为 `SYSTEM_INSTRUCTION`。
  - 提示词**按行变化**（task_203 5 种、task_211 2 种）→ 逐行拼接进 `input`（`"提示词\n\n问题"`），不设系统提示词。
  - **无提示词**（task_201/202/204/205/207/208，列为空或 "/" 或无此列）→ 不设系统提示词。
- 测试命令：`/opt/anaconda3/bin/python -m pytest tests/test_20260821_qbank_tasks.py -v`。

---
### Task 1: 构建脚本（数据转换部分）+ 生成 11 个 jsonl

**Files:**
- Create: `scripts/build_20260821_qbank_tasks.py`
- Test: `tests/test_20260821_qbank_tasks.py`

**Interfaces:**
- Produces: `build_records(task: dict) -> (list[dict], str|None)` — 读取一个 xlsx，返回 `[{"input","output"}]` 与系统提示词；`TASKS` 模块级清单（11 个任务配置）。

- [ ] **Step 1: 写构建脚本（数据转换部分）**

```python
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
20260821 各专业题库 -> 评测任务 批量构建

读取 mydata/20260821专业题库测试 下 11 个 xlsx，生成：
1. data/custom_task/task_2NN.jsonl（每行 {"input","output"}）
2. ais_bench/benchmark/configs/datasets/custom_task/task_2NN_suite.py
3. docs/20260821专业题库任务映射.md
"""

import json
from collections import Counter
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent.parent
DATA_SRC = ROOT / "mydata" / "20260821专业题库测试"
DATA_OUT = ROOT / "data" / "custom_task"
SUITE_OUT = ROOT / "ais_bench" / "benchmark" / "configs" / "datasets" / "custom_task"
DOC_OUT = ROOT / "docs" / "20260821专业题库任务映射.md"

# prompt_mode:
#   system -> 提示词恒定，取列众数作为 SYSTEM_INSTRUCTION
#   fold   -> 提示词按行变化，拼接进 input（"提示词\n\n问题"）
#   none   -> 无提示词（列为空/"/" 或无此列）
TASKS = [
    dict(task_id=201, name="资源管理-知识理解", cap="知识理解",
         file="资源管理/基础题库/资源管理-知识理解（问题-input, 答案-output）.xlsx",
         prompt_mode="none", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=202, name="传输网-知识理解", cap="知识理解",
         file="传输网/基础题库/传输-知识理解.xlsx",
         prompt_mode="none", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=203, name="代维-知识理解", cap="知识理解",
         file="代维/基础题库/代维-知识理解.xlsx",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=204, name="个人业务-知识理解", cap="知识理解",
         file="个人业务/基础题库/个人业务-知识理解.xlsx",
         prompt_mode="none", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=205, name="核心网-知识理解", cap="知识理解",
         file="核心网/基础题库/核心网-知识理解.xlsx",
         prompt_mode="none", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=206, name="基础保障-知识理解", cap="知识理解",
         file="基础保障/基础题库/基础保障-知识理解.xlsx",
         prompt_mode="system", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=207, name="监控排障-知识理解", cap="知识理解",
         file="监控排障/基础题库/监控-知识理解.xlsx",
         prompt_mode="none", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=208, name="网络投诉-知识理解", cap="知识理解",
         file="网络投诉/基础题库/监控（投诉）-知识理解.xlsx",
         prompt_mode="none", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=209, name="个人业务-意图识别", cap="意图识别",
         file="个人业务/基础题库/个人业务-意图识别.xlsx",
         prompt_mode="system", evaluator="JsonFieldEvaluator",
         field_config={"intent": {"match_type": "exact", "weight": 1.0},
                       "entities": {"match_type": "exact", "weight": 0.0}}),
    dict(task_id=210, name="核心网-意图识别", cap="意图识别",
         file="核心网/基础题库/核心网-意图识别.xlsx",
         prompt_mode="system", evaluator="JsonFieldEvaluator",
         field_config={"分类结果": {"match_type": "exact", "weight": 1.0},
                       "分类标号": {"match_type": "exact", "weight": 1.0}}),
    dict(task_id=211, name="监控排障-意图识别", cap="意图识别",
         file="监控排障/基础题库/监控-意图识别.xlsx",
         prompt_mode="fold", evaluator="AccEvaluator"),
]


def build_records(task):
    """读取一个 xlsx，返回 (records: list[dict], system: str|None)。"""
    path = DATA_SRC / task["file"]
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb.worksheets[0]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()

    header = rows[0]
    idx = {}
    for i, name in enumerate(header):
        name = str(name).strip() if name is not None else ""
        if name in ("问题", "input"):
            idx.setdefault("question", i)
        elif name in ("答案", "output"):
            idx.setdefault("answer", i)
        elif name == "提示词":
            idx["prompt"] = i

    qc, ac, pc = idx["question"], idx["answer"], idx.get("prompt")

    prompt_counter = Counter()
    records = []
    for r in rows[1:]:
        q = str(r[qc]).strip() if r[qc] is not None else ""
        a = str(r[ac]).strip() if r[ac] is not None else ""
        if not q or not a:
            continue  # 空行或缺失 问题/答案
        p = str(r[pc]).strip() if pc is not None and r[pc] is not None else ""
        if p and p != "/":
            prompt_counter[p] += 1
            if task["prompt_mode"] == "fold":
                q = p + "\n\n" + q
        records.append({"input": q, "output": a})

    system = None
    if task["prompt_mode"] == "system":
        if not prompt_counter:
            raise ValueError(f"task_{task['task_id']} prompt_mode=system 但提示词列为空")
        system = prompt_counter.most_common(1)[0][0]
    return records, system


def write_data(records, task):
    out = DATA_OUT / f"task_{task['task_id']}.jsonl"
    with open(out, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def main():
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    SUITE_OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for task in TASKS:
        records, system = build_records(task)
        write_data(records, task)
        total += len(records)
        print(f"✅ task_{task['task_id']} {task['name']}: {len(records)} 条, "
              f"system={'有' if system else '无'}")
    print(f"总计 {total} 条")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: 写测试（数据部分）**

```python
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
```

- [ ] **Step 3: 运行构建脚本，生成数据**

Run: `/opt/anaconda3/bin/python scripts/build_20260821_qbank_tasks.py`
Expected: 打印 11 行 `✅ task_NNN ...: NNN 条`，总计 3675 条；task_201 774、task_202 175、task_203 300、task_204 196、task_205 100、task_206 550、task_207 198、task_208 129、task_209 200、task_210 1007、task_211 46。

- [ ] **Step 4: 跑测试，验证数据**

Run: `/opt/anaconda3/bin/python -m pytest tests/test_20260821_qbank_tasks.py -v`
Expected: 22 个测试全部 PASS。

- [ ] **Step 5: 抽检与源文件一致性**

Run: `/opt/anaconda3/bin/python - <<'EOF'
import json, openpyxl
from pathlib import Path
R = Path('data/custom_task')
src = Path('mydata/20260821专业题库测试')
# task_201 资源管理前3条
recs = [json.loads(l) for l in (R/'task_201.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
wb = openpyxl.load_workbook(src/'资源管理/基础题库/资源管理-知识理解（问题-input, 答案-output）.xlsx', read_only=True, data_only=True)
rows = list(wb.worksheets[0].iter_rows(values_only=True)); wb.close()
print('jsonl[0].input == xlsx row2 col3:', recs[0]['input'] == str(rows[1][2]).strip())
print('jsonl[0].output == xlsx row2 col4:', recs[0]['output'] == str(rows[1][3]).strip())
EOF`
Expected: 两个 `True`。

- [ ] **Step 6: Commit**

```bash
git add scripts/build_20260821_qbank_tasks.py tests/test_20260821_qbank_tasks.py data/custom_task/task_20*.jsonl data/custom_task/task_211.jsonl
git commit -m "feat: build 11 qbank eval datasets (task_201-211) from 20260821 professional question bank

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---
### Task 2: suite 生成 + 导入/评估器验证

**Files:**
- Modify: `scripts/build_20260821_qbank_tasks.py`（新增 `build_suite_content`、`write_suite`，main 中调用）
- Test: `tests/test_20260821_qbank_tasks.py`（新增 suite 导入测试）

**Interfaces:**
- Consumes: `TASKS`、`build_records` 的返回值 `system`
- Produces: `build_suite_content(task: dict, system: str|None) -> str`；11 个 `task_NNN_suite.py`

- [ ] **Step 1: 在脚本中追加 suite 生成函数**

在 `write_data` 函数后追加：

```python
import pprint

# 导入行（按评估器插入）
_IMPORTS = [
    "from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate",
    "from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever",
    "from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer",
    "from ais_bench.benchmark.datasets.custom import CustomDataset",
]
_EVAL_IMPORT = {
    "TelecomLLMJudgeEvaluator": "from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator",
    "JsonFieldEvaluator": "from ais_bench.benchmark.openicl.icl_evaluator import JsonFieldEvaluator",
    "AccEvaluator": "from ais_bench.benchmark.openicl.icl_evaluator import AccEvaluator",
}


def build_suite_content(task, system):
    tid = task["task_id"]
    ev = task["evaluator"]
    imports = _IMPORTS[:3] + [_EVAL_IMPORT[ev]] + _IMPORTS[3:]

    if ev == "TelecomLLMJudgeEvaluator":
        eval_block = "    evaluator=dict(type=TelecomLLMJudgeEvaluator),"
    elif ev == "JsonFieldEvaluator":
        fc = pprint.pformat(task["field_config"], width=72, sort_dicts=False)
        eval_block = (
            "    evaluator=dict(\n"
            "        type=JsonFieldEvaluator,\n"
            f"        field_config={fc},\n"
            "        default_match_type='exact',\n"
            "        return_details=True,\n"
            "        strict_mode=True,\n"
            "    ),"
        )
    else:
        eval_block = "    evaluator=dict(type=AccEvaluator),"

    system_section = ""
    begin_block = ""
    if system is not None:
        system_section = (
            f"\n# 该任务固定的系统提示词（取自源文件提示词列众数）\n"
            f"SYSTEM_INSTRUCTION = {json.dumps(system, ensure_ascii=False)}\n"
        )
        begin_block = (
            "            begin=[\n"
            "                dict(role='SYSTEM', fallback_role='HUMAN', prompt=SYSTEM_INSTRUCTION),\n"
            "            ],\n"
        )

    content = (
        "\n".join(imports)
        + f"\n\n# task_{tid}: {task['name']}\n# Metric: {ev}"
        + system_section
        + f"\ntask_{tid}_reader_cfg = dict(\n"
        + "    input_columns=['input'],\n    output_column='output',\n)\n"
        + f"\ntask_{tid}_infer_cfg = dict(\n"
        + "    prompt_template=dict(\n        type=PromptTemplate,\n        template=dict(\n"
        + begin_block
        + "            round=[\n"
        + "                dict(role='HUMAN', prompt='{input}'),\n"
        + "                dict(role='BOT', prompt=''),\n            ],\n"
        + "        ),\n    ),\n"
        + "    retriever=dict(type=ZeroRetriever),\n"
        + "    inferencer=dict(type=GenInferencer),\n)\n"
        + f"\ntask_{tid}_eval_cfg = dict(\n{eval_block}\n)\n"
        + f"\n# 导出数据集配置\ntask_{tid}_datasets = [\n"
        + "    dict(\n        type=CustomDataset,\n"
        + f"        abbr='task_{tid}',\n        path='data/custom_task/task_{tid}.jsonl',\n"
        + f"        reader_cfg=task_{tid}_reader_cfg,\n"
        + f"        infer_cfg=task_{tid}_infer_cfg,\n"
        + f"        eval_cfg=task_{tid}_eval_cfg,\n    )\n]\n"
    )
    return content


def write_suite(task, system):
    out = SUITE_OUT / f"task_{task['task_id']}_suite.py"
    out.write_text(build_suite_content(task, system), encoding="utf-8")
```

- [ ] **Step 2: main() 中调用 write_suite**

将 main() 改为：

```python
def main():
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    SUITE_OUT.mkdir(parents=True, exist_ok=True)
    total = 0
    for task in TASKS:
        records, system = build_records(task)
        write_data(records, task)
        write_suite(task, system)
        total += len(records)
        print(f"✅ task_{task['task_id']} {task['name']}: {len(records)} 条, "
              f"system={'有' if system else '无'}")
    print(f"总计 {total} 条")
```

- [ ] **Step 3: 测试文件追加 suite 导入测试**

在 `tests/test_20260821_qbank_tasks.py` 末尾追加：

```python
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
```

- [ ] **Step 4: 重跑脚本生成 suite**

Run: `/opt/anaconda3/bin/python scripts/build_20260821_qbank_tasks.py`
Expected: 与 Task 1 Step 3 相同输出，且 `ais_bench/benchmark/configs/datasets/custom_task/task_2NN_suite.py` 11 个文件生成。

- [ ] **Step 5: 跑全部测试**

Run: `/opt/anaconda3/bin/python -m pytest tests/test_20260821_qbank_tasks.py -v`
Expected: 33 个测试全部 PASS（22 数据 + 11 suite）。

- [ ] **Step 6: 人工核对一个 suite 内容**

Run: `cat ais_bench/benchmark/configs/datasets/custom_task/task_210_suite.py`
Expected: 含 `SYSTEM_INSTRUCTION = "你是一位故障分类专家，擅于对投诉信息进行分类..."`（task_43 同款）、`JsonFieldEvaluator`、`field_config` 含"分类结果/分类标号"。
再 `cat ais_bench/benchmark/configs/datasets/custom_task/task_211_suite.py`：
Expected: 无 `SYSTEM_INSTRUCTION`，`round` 前无 `begin`，`AccEvaluator`。

- [ ] **Step 7: Commit**

```bash
git add ais_bench/benchmark/configs/datasets/custom_task/task_20*.py ais_bench/benchmark/configs/datasets/custom_task/task_211_suite.py tests/test_20260821_qbank_tasks.py scripts/build_20260821_qbank_tasks.py
git commit -m "feat: add eval suites for qbank tasks task_201-211

Co-Authored-By: Claude <noreply@anthropic.com>"
```

---
### Task 3: 映射文档 + 全量验证

**Files:**
- Modify: `scripts/build_20260821_qbank_tasks.py`（新增 `write_doc`，main 中调用）
- Create: `docs/20260821专业题库任务映射.md`（由脚本生成）

- [ ] **Step 1: 追加 write_doc 并在 main 调用**

```python
def write_doc(summaries):
    lines = [
        "# 20260821 各专业题库评测任务映射",
        "",
        "数据来源：`mydata/20260821专业题库测试`。构建范围：进度跟踪表第 2、3 行（知识理解 + 意图识别）。",
        "",
        "| 任务编号 | 数据集名 | 能力 | 源文件 | 评估器 | 系统提示词 | 实际条数 |",
        "|---------|---------|------|--------|--------|-----------|---------|",
    ]
    mode_note = {"system": "有", "fold": "拼入input", "none": "无"}
    for task, n in summaries:
        lines.append(
            f"| task_{task['task_id']} | {task['name']} | {task['cap']} | "
            f"`{task['file']}` | {task['evaluator']} | "
            f"{mode_note[task['prompt_mode']]} | {n} |"
        )
    lines += [
        "",
        "> 说明：",
        "> - task_210 源文件 1007 行，进度跟踪表标注 1911（未与专业确认），以实际文件数据行为准。",
        "> - task_203/211 提示词按行变化，已逐行拼入 input，不设系统提示词。",
        "> - task_206/209/210 提示词恒定，取列众数作为 SYSTEM_INSTRUCTION。",
    ]
    DOC_OUT.parent.mkdir(parents=True, exist_ok=True)
    DOC_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"📄 映射文档: {DOC_OUT}")
```

main() 末尾改为：

```python
    print(f"总计 {total} 条")
    write_doc([(t, len(build_records(t)[0])) for t in TASKS])
```

- [ ] **Step 2: 重跑脚本生成文档**

Run: `/opt/anaconda3/bin/python scripts/build_20260821_qbank_tasks.py`
Expected: 打印 11 行 ✅ 与总计 3675，最后一行 `📄 映射文档: docs/20260821专业题库任务映射.md`。

- [ ] **Step 3: 全量测试 + 文档行数核对**

Run: `/opt/anaconda3/bin/python -m pytest tests/test_20260821_qbank_tasks.py -v`
Expected: 33 个测试 PASS。
再 Run: `grep -c "^| task_" docs/20260821专业题库任务映射.md`
Expected: `11`。

- [ ] **Step 4: 端到端冒烟（可选，需推理模型配置）**

Run: `grep -c "" data/custom_task/task_2*.jsonl`
Expected: 11 行，各文件行数 = 期望条数（774/175/300/196/100/550/198/129/200/1007/46）。

- [ ] **Step 5: Commit**

```bash
git add scripts/build_20260821_qbank_tasks.py docs/20260821专业题库任务映射.md
git commit -m "docs: add qbank task mapping table (task_201-211)

Co-Authored-By: Claude <noreply@anthropic.com>"
```
