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
