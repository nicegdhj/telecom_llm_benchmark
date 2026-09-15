#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
20260908 评测数据集 -> 评测任务 批量构建（全量数据，合并版）

59 个文件 → 38 个有效任务：
  - 26 个非合并 task（2段式命名，单数据集）
  - 12 个合并 task（3段式命名汇聚，多子数据集列表）

合并规则：
  - 同一汇聚类（前两段相同）的多个文件合并为一个 task_NNN
  - 数据文件放 custom_task/task_NNN/ 下（type1.jsonl, type2.jsonl, ...）
  - suite 用多子数据集列表（参照 tele_exam 模式）
  - system 提示词统一拼入 input（fold 模式），不设 SYSTEM_INSTRUCTION
  - 评估器：同一汇聚类内统一

汇聚准确率 = Σ(各子类正确数) / Σ(各子类总数)（eval_judge.py 自动按 suite 汇聚）
"""

import json
import shutil
import pprint
from collections import Counter
from pathlib import Path

import openpyxl

ROOT = Path(__file__).parent.parent
DATA_SRC = ROOT / "mydata" / "20260908评测数据集"
DATA_OUT = ROOT / "data" / "custom_task"
SUITE_OUT = ROOT / "ais_bench" / "benchmark" / "configs" / "datasets" / "custom_task"
DOC_OUT = ROOT / "docs" / "20260821专业题库任务映射.md"

# ══════════════════════════════════════════════════════════════════
# 非合并任务（2段式，单数据集）
# ══════════════════════════════════════════════════════════════════
SIMPLE_TASKS = [
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
    dict(task_id=211, name="监控排障-意图识别", cap="意图识别",
         file="监控排障/基础题库/监控-意图识别.xlsx",
         prompt_mode="fold", evaluator="AccEvaluator"),
    dict(task_id=212, name="家客-知识理解", cap="知识理解",
         file="家客/基础题库/家客-知识理解.xlsx",
         prompt_mode="none", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=213, name="集客-知识理解", cap="知识理解",
         file="集客/基础题库/集客-知识理解.xlsx",
         prompt_mode="none", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=215, name="监控排障-参数提取", cap="参数提取",
         file="监控排障/基础题库/监控-参数提取.xlsx",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=216, name="个人业务-自主规划", cap="自主规划",
         file="个人业务/高阶题库/个人业务-自主规划.xlsx",
         prompt_mode="system", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=217, name="代维-自主规划", cap="自主规划",
         file="代维/高阶题库/代维-自主规划.xlsx",
         prompt_mode="system", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=218, name="监控排障-自主规划", cap="自主规划",
         file="监控排障/高阶题库/监控-自主规划.xlsx",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=219, name="网络投诉-自主规划", cap="自主规划",
         file="网络投诉/高阶题库/监控（投诉）-自主规划.xlsx",
         prompt_mode="system", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=220, name="资源管理-自主规划", cap="自主规划",
         file="资源管理/高阶题库/资源管理-自主规划.xlsx",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=221, name="个人业务-诊断分析", cap="诊断分析",
         file="个人业务/高阶题库/个人业务-诊断分析.xlsx",
         prompt_mode="system", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=222, name="代维-诊断分析", cap="诊断分析",
         file="代维/高阶题库/代维-诊断分析.xlsx",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=223, name="传输网-诊断分析", cap="诊断分析",
         file="传输网/高阶题库/传输-诊断分析.xlsx",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=224, name="基础保障-诊断分析", cap="诊断分析",
         file="基础保障/高阶题库/基础保障-诊断分析.xlsx",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=226, name="监控排障-诊断分析", cap="诊断分析",
         file="监控排障/高阶题库/监控-诊断分析.xlsx",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=227, name="资源管理-诊断分析", cap="诊断分析",
         file="资源管理/高阶题库/资源管理-诊断分析.xlsx",
         prompt_mode="system", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=234, name="入口智能体-测试集", cap="入口智能体",
         file="入口智能体/入口_测试集10_sharegpt.json",
         prompt_mode="fold", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=235, name="安全-诊断分析", cap="诊断分析",
         file="安全/高阶题库/安全-诊断分析.json",
         prompt_mode="system", evaluator="TelecomLLMJudgeEvaluator"),
    dict(task_id=247, name="家客-诊断分析", cap="诊断分析",
         file="家客/高阶题库/家客-诊断分析.json",
         prompt_mode="system", evaluator="TelecomLLMJudgeEvaluator"),
]

# ══════════════════════════════════════════════════════════════════
# 合并任务（3段式汇聚，多子数据集）
# 每个汇聚类的子任务合并为一个 task，数据放 task_NNN/ 目录下
# ══════════════════════════════════════════════════════════════════
MERGED_GROUPS = [
    dict(task_id=209, name="个人业务-意图识别", cap="意图识别",
         evaluator="JsonFieldEvaluator",
         field_config={"intent": {"match_type": "exact", "weight": 1.0},
                       "entities": {"match_type": "exact", "weight": 0.0},
                       "confidence": {"match_type": "exact", "weight": 0.0}},
         sub_tasks=[
             dict(label="任务1", file="个人业务/基础题库/个人业务-意图识别-任务1.xlsx"),
             dict(label="任务2", file="个人业务/基础题库/个人业务-意图识别-任务2.json"),
         ]),
    dict(task_id=210, name="核心网-意图识别-分类", cap="意图识别",
         evaluator="JsonFieldEvaluator",
         field_config={"分类结果": {"match_type": "exact", "weight": 1.0},
                       "分类标号": {"match_type": "exact", "weight": 1.0}},
         sub_tasks=[
             dict(label="分类1", file="核心网/基础题库/核心网-意图识别-分类1.json"),
             dict(label="分类2", file="核心网/基础题库/核心网-意图识别-分类2.json"),
         ]),
    dict(task_id=214, name="个人业务-参数提取", cap="参数提取",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="任务1", file="个人业务/基础题库/个人业务-参数提取-任务1.xlsx"),
             dict(label="任务2", file="个人业务/基础题库/个人业务-参数提取-任务2.json"),
             dict(label="任务3", file="个人业务/基础题库/个人业务-参数提取-任务3.json"),
         ]),
    dict(task_id=225, name="核心网-诊断分析", cap="诊断分析",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="任务1", file="核心网/高阶题库/核心网-诊断分析-任务1.xlsx"),
             dict(label="任务2", file="核心网/高阶题库/核心网-诊断分析-任务2.json"),
             dict(label="任务3", file="核心网/高阶题库/核心网-诊断分析-任务3.json"),
         ]),
    dict(task_id=229, name="核心网-意图识别-参数提取", cap="意图识别",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="参数提取1", file="核心网/基础题库/核心网-意图识别-参数提取1.json"),
             dict(label="参数提取2", file="核心网/基础题库/核心网-意图识别-参数提取2.json"),
         ]),
    dict(task_id=236, name="家客-意图识别+信息提取", cap="意图识别",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="任务1", file="家客/基础题库/家客-意图识别+信息提取-任务1.json"),
             dict(label="任务2", file="家客/基础题库/家客-意图识别+信息提取-任务2.json"),
             dict(label="任务3", file="家客/基础题库/家客-意图识别+信息提取-任务3.json"),
             dict(label="任务4", file="家客/基础题库/家客-意图识别+信息提取-任务4.json"),
         ]),
    dict(task_id=240, name="家客-意图识别-分类", cap="意图识别",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="分类1", file="家客/基础题库/家客-意图识别-分类1.json"),
             dict(label="分类2", file="家客/基础题库/家客-意图识别-分类2.json"),
             dict(label="分类3", file="家客/基础题库/家客-意图识别-分类3.json"),
             dict(label="分类4", file="家客/基础题库/家客-意图识别-分类4.json"),
             dict(label="分类5", file="家客/基础题库/家客-意图识别-分类5.json"),
             dict(label="分类6", file="家客/基础题库/家客-意图识别-分类6.json"),
             dict(label="分类7", file="家客/基础题库/家客-意图识别-分类7.json"),
         ]),
    dict(task_id=250, name="网络投诉-信息提取", cap="参数提取",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="任务1", file="网络投诉/基础题库/监控（投诉）-信息提取-任务1.json"),
             dict(label="任务2", file="网络投诉/基础题库/监控（投诉）-信息提取-任务2.json"),
             dict(label="任务3", file="网络投诉/基础题库/监控（投诉）-信息提取-任务3.json"),
         ]),
    dict(task_id=253, name="网络投诉-意图识别", cap="意图识别",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="任务1", file="网络投诉/基础题库/监控（投诉）-意图识别-任务1.json"),
             dict(label="任务2", file="网络投诉/基础题库/监控（投诉）-意图识别-任务2.json"),
             dict(label="任务3", file="网络投诉/基础题库/监控（投诉）-意图识别-任务3.json"),
         ]),
    dict(task_id=256, name="集客-参数提取", cap="参数提取",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="任务1", file="集客/基础题库/集客-参数提取-任务1.json"),
             dict(label="任务2", file="集客/基础题库/集客-参数提取-任务2.json"),
         ]),
    dict(task_id=258, name="集客-意图识别", cap="意图识别",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="任务1", file="集客/基础题库/集客-意图识别-任务1.json"),
             dict(label="任务2", file="集客/基础题库/集客-意图识别-任务2.json"),
         ]),
    dict(task_id=260, name="集客-诊断分析", cap="诊断分析",
         evaluator="TelecomLLMJudgeEvaluator",
         sub_tasks=[
             dict(label="任务1", file="集客/高阶题库/集客-诊断分析-任务1.json"),
             dict(label="任务2", file="集客/高阶题库/集客-诊断分析-任务2.json"),
             dict(label="任务3", file="集客/高阶题库/集客-诊断分析-任务3.json"),
         ]),
]

# 废弃的 task 编号（原3段式任务中被合并掉的）
DEPRECATED_TASKS = [
    228, 231, 232, 233, 237, 238, 239, 241, 242, 243, 244, 245, 246,
    248, 249, 251, 252, 254, 255, 257, 259, 261, 262,
]


# ══════════════════════════════════════════════════════════════════
# 数据解析函数
# ══════════════════════════════════════════════════════════════════

def build_records_from_xlsx(filepath, prompt_mode="system"):
    """读取 xlsx，返回 (records, system)。prompt_mode 统一 fold 化处理。"""
    wb = openpyxl.load_workbook(filepath, read_only=True, data_only=True)
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
            continue
        p = str(r[pc]).strip() if pc is not None and r[pc] is not None else ""
        if p and p != "/":
            prompt_counter[p] += 1
            q = p + "\n\n" + q
        records.append({"input": q, "output": a})

    system = None
    if prompt_mode == "system" and prompt_counter:
        system = prompt_counter.most_common(1)[0][0]
    return records, system


def build_records_from_json(filepath, prompt_mode="system"):
    """读取 sharegpt json，返回 (records, system)。"""
    with open(filepath, "r", encoding="utf-8") as f:
        data = json.load(f)

    prompt_counter = Counter()
    records = []
    for item in data:
        convs = item.get("conversations", [])
        if len(convs) < 2:
            continue
        q = str(convs[0].get("value", "")).strip()
        a = str(convs[1].get("value", "")).strip()
        if not q or not a:
            continue
        s = str(item.get("system", "")).strip()
        if s:
            prompt_counter[s] += 1
            q = s + "\n\n" + q
        records.append({"input": q, "output": a})

    system = None
    if prompt_mode == "system" and prompt_counter:
        system = prompt_counter.most_common(1)[0][0]
    return records, system


def build_records(filepath, prompt_mode="system"):
    """根据文件扩展名选择解析方式。统一把 system 拼入 input（fold 化）。"""
    if filepath.suffix == ".json":
        return build_records_from_json(filepath, prompt_mode)
    else:
        return build_records_from_xlsx(filepath, prompt_mode)


# ══════════════════════════════════════════════════════════════════
# Suite 生成
# ══════════════════════════════════════════════════════════════════

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


def _eval_block(task_or_group):
    ev = task_or_group["evaluator"]
    if ev == "JsonFieldEvaluator":
        fc = pprint.pformat(task_or_group["field_config"], width=72, sort_dicts=False)
        return (
            "    evaluator=dict(\n"
            "        type=JsonFieldEvaluator,\n"
            f"        field_config={fc},\n"
            "        default_match_type='exact',\n"
            "        return_details=True,\n"
            "        strict_mode=True,\n"
            "    ),"
        )
    elif ev == "TelecomLLMJudgeEvaluator":
        return "    evaluator=dict(type=TelecomLLMJudgeEvaluator),"
    else:
        return "    evaluator=dict(type=AccEvaluator),"


def build_simple_suite(task, system):
    """生成单数据集 suite 文件内容。"""
    tid = task["task_id"]
    ev = task["evaluator"]
    imports = _IMPORTS[:3] + [_EVAL_IMPORT[ev]] + _IMPORTS[3:]

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
        + f"\ntask_{tid}_eval_cfg = dict(\n{_eval_block(task)}\n)\n"
        + f"\n# 导出数据集配置\ntask_{tid}_datasets = [\n"
        + "    dict(\n        type=CustomDataset,\n"
        + f"        abbr='task_{tid}',\n        path='data/custom_task/task_{tid}.jsonl',\n"
        + f"        reader_cfg=task_{tid}_reader_cfg,\n"
        + f"        infer_cfg=task_{tid}_infer_cfg,\n"
        + f"        eval_cfg=task_{tid}_eval_cfg,\n    )\n]\n"
    )
    return content


def build_merged_suite(group):
    """生成多子数据集汇聚 suite 文件内容（参照 tele_exam 模式）。"""
    tid = group["task_id"]
    ev = group["evaluator"]
    imports = _IMPORTS[:3] + [_EVAL_IMPORT[ev]] + _IMPORTS[3:]

    sub_labels = [st["label"] for st in group["sub_tasks"]]

    content = "\n".join(imports)
    content += f"\n\n# task_{tid}: {group['name']}（汇聚任务，{len(sub_labels)}个子分类）\n"
    content += f"# Metric: {ev}\n"
    content += f"# 子分类: {', '.join(sub_labels)}\n"
    content += f"# 数据目录: data/custom_task/task_{tid}/\n"
    content += f"# 汇聚准确率 = Σ(各子类正确数) / Σ(各子类总数)\n"
    content += f"\ntask_{tid}_sub_sets = {json.dumps(sub_labels, ensure_ascii=False)}\n"
    content += f"\ntask_{tid}_reader_cfg = dict(\n    input_columns=['input'],\n    output_column='output',\n)\n"
    content += (
        f"\ntask_{tid}_infer_cfg = dict(\n"
        "    prompt_template=dict(\n        type=PromptTemplate,\n        template=dict(\n"
        "            round=[\n"
        "                dict(role='HUMAN', prompt='{input}'),\n"
        "                dict(role='BOT', prompt=''),\n            ],\n"
        "        ),\n    ),\n"
        "    retriever=dict(type=ZeroRetriever),\n"
        "    inferencer=dict(type=GenInferencer),\n)\n"
    )
    content += f"\ntask_{tid}_eval_cfg = dict(\n{_eval_block(group)}\n)\n"
    content += (
        f"\n# 导出数据集配置（多子数据集列表，ais_bench 分别推理+评测，eval_judge 自动汇聚）\n"
        f"task_{tid}_datasets = []\n"
        f"for _name in task_{tid}_sub_sets:\n"
        f"    task_{tid}_datasets.append(\n"
        f"        dict(\n            type=CustomDataset,\n"
        f"            abbr=f'task_{tid}_{{_name}}',\n"
        f"            path=f'data/custom_task/task_{tid}/{{_name}}.jsonl',\n"
        f"            reader_cfg=task_{tid}_reader_cfg,\n"
        f"            infer_cfg=task_{tid}_infer_cfg,\n"
        f"            eval_cfg=task_{tid}_eval_cfg,\n        )\n    )\n"
        f"\ndel _name\n"
    )
    return content


# ══════════════════════════════════════════════════════════════════
# 文档生成
# ══════════════════════════════════════════════════════════════════

def write_doc(simple_summaries, merged_summaries):
    lines = [
        "# 20260821 各专业题库评测任务映射",
        "",
        "数据来源：`mydata/20260908评测数据集`（全量数据，59 个文件 → 38 个有效任务）。",
        "",
        "## 非合并任务（26个，单数据集）",
        "",
        "| 任务编号 | 数据集名 | 能力 | 源文件 | 评估器 | 系统提示词 | 条数 |",
        "|---------|---------|------|--------|--------|-----------|------|",
    ]
    mode_note = {"system": "有", "fold": "拼入input", "none": "无"}
    for task, n, _ in simple_summaries:
        lines.append(
            f"| task_{task['task_id']} | {task['name']} | {task['cap']} | "
            f"`{task['file']}` | {task['evaluator']} | "
            f"{mode_note[task['prompt_mode']]} | {n} |"
        )

    lines += [
        "",
        "## 合并任务（12个，多子数据集汇聚）",
        "",
        "| 任务编号 | 汇聚类 | 能力 | 子分类数 | 评估器 | 子分类列表 | 总条数 |",
        "|---------|--------|------|---------|--------|-----------|-------|",
    ]
    for group, sub_counts, total in merged_summaries:
        labels = [st["label"] for st in group["sub_tasks"]]
        lines.append(
            f"| task_{group['task_id']} | {group['name']} | {group['cap']} | "
            f"{len(labels)} | {group['evaluator']} | "
            f"{', '.join(labels)} | {total} |"
        )

    lines += [
        "",
        "## 废弃任务（23个，已合并到上述汇聚类）",
        "",
        f"编号: {', '.join(str(t) for t in DEPRECATED_TASKS)}",
        "",
        "> 说明：",
        "> - 3段式命名的文件按前两段汇聚为一个 task，数据放 `custom_task/task_NNN/` 目录下。",
        "> - 合并 task 的 suite 用多子数据集列表（参照 tele_exam 模式），ais_bench 分别推理+评测。",
        "> - 汇聚准确率 = Σ(各子类正确数) / Σ(各子类总数)（eval_judge.py 自动按 suite 汇聚）。",
        "> - system 提示词统一拼入 input（fold 化），不设 SYSTEM_INSTRUCTION。",
        "> - LLM Judge 类型任务用 `llm_judge_percentage` 作为准确率指标。",
    ]
    DOC_OUT.parent.mkdir(parents=True, exist_ok=True)
    DOC_OUT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"📄 映射文档: {DOC_OUT}")


# ══════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════

def main():
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    SUITE_OUT.mkdir(parents=True, exist_ok=True)

    # 清理废弃的旧文件
    for tid in DEPRECATED_TASKS:
        old_suite = SUITE_OUT / f"task_{tid}_suite.py"
        old_jsonl = DATA_OUT / f"task_{tid}.jsonl"
        if old_suite.exists():
            old_suite.unlink()
            print(f"🗑️ 删除废弃 suite: task_{tid}_suite.py")
        if old_jsonl.exists():
            old_jsonl.unlink()
            print(f"🗑️ 删除废弃 jsonl: task_{tid}.jsonl")

    simple_summaries = []
    merged_summaries = []
    grand_total = 0

    # 1. 非合并任务
    print("\n═══ 非合并任务（单数据集）═══")
    for task in SIMPLE_TASKS:
        filepath = DATA_SRC / task["file"]
        records, system = build_records(filepath, task["prompt_mode"])
        # 写入 jsonl
        out = DATA_OUT / f"task_{task['task_id']}.jsonl"
        with open(out, "w", encoding="utf-8") as f:
            for rec in records:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        # 写入 suite
        suite_out = SUITE_OUT / f"task_{task['task_id']}_suite.py"
        suite_out.write_text(build_simple_suite(task, system), encoding="utf-8")
        grand_total += len(records)
        simple_summaries.append((task, len(records), system))
        print(f"✅ task_{task['task_id']} {task['name']}: {len(records)} 条")

    # 2. 合并任务
    print("\n═══ 合并任务（多子数据集汇聚）═══")
    for group in MERGED_GROUPS:
        tid = group["task_id"]
        task_dir = DATA_OUT / f"task_{tid}"
        task_dir.mkdir(parents=True, exist_ok=True)

        sub_counts = []
        group_total = 0
        for sub in group["sub_tasks"]:
            filepath = DATA_SRC / sub["file"]
            records, _ = build_records(filepath, "system")
            # 写入子分类 jsonl
            out = task_dir / f"{sub['label']}.jsonl"
            with open(out, "w", encoding="utf-8") as f:
                for rec in records:
                    f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            sub_counts.append(len(records))
            group_total += len(records)

        # 写入汇聚 suite
        suite_out = SUITE_OUT / f"task_{tid}_suite.py"
        suite_out.write_text(build_merged_suite(group), encoding="utf-8")
        grand_total += group_total
        merged_summaries.append((group, sub_counts, group_total))
        labels = [st["label"] for st in group["sub_tasks"]]
        counts_str = ", ".join(f"{l}={c}" for l, c in zip(labels, sub_counts))
        print(f"✅ task_{tid} {group['name']}: {group_total} 条 ({counts_str})")

    print(f"\n总计 {grand_total} 条（{len(SIMPLE_TASKS)} 非合并 + {len(MERGED_GROUPS)} 合并 = {len(SIMPLE_TASKS) + len(MERGED_GROUPS)} 个有效任务）")
    write_doc(simple_summaries, merged_summaries)


if __name__ == "__main__":
    main()
