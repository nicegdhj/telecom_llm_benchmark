#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
reeval_telechat.py - 针对 telechat-36b 对 3 个 0 分任务重新评测

背景：telechat-36b 输出的是 inline 推理链（无 <think> 标签），导致：
  - task_34 / task_36：AccEvaluator 精确匹配全失败（正确答案嵌在推理文本末尾）
  - BFCL：函数调用格式为 Python-like，与 JSON gold 格式不符

修复逻辑（仅针对 telechat-36b）：
  - task_34：从 prediction 末尾提取最后一个数字 0-4
  - task_36：从 prediction 末尾提取最后出现的 Yes 或 No
  - BFCL：提取末尾 [...] 块，用 default_decode_ast_prompting 解析，再用 ast_checker 匹配

用法：
    conda run -n ais_bench python scripts/reeval_telechat.py \
        --fmt-dir /Users/jia/windowsShare/fmt0416_common \
        --model telechat-36b \
        --eval-version eval_init
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ── 导入 bfcl_eval（仅在 ais_bench 环境中可用）────────────────────────────
try:
    from bfcl_eval.model_handler.utils import default_decode_ast_prompting
    from bfcl_eval.eval_checker.ast_eval.ast_checker import ast_checker
    from bfcl_eval.utils import is_function_calling_format_output
    BFCL_AVAILABLE = True
except ImportError:
    BFCL_AVAILABLE = False
    print("⚠️  bfcl_eval 未安装，跳过 BFCL 重评测", file=sys.stderr)


# ══════════════════════════════════════════════════════════════════════════════
# 后处理：提取答案
# ══════════════════════════════════════════════════════════════════════════════

def extract_digit_0_4(pred: str) -> str:
    """从 prediction 末尾提取最后出现的数字 0-4（task_34 专用）"""
    matches = re.findall(r'[0-4]', pred)
    return matches[-1] if matches else ""


def extract_yes_no(pred: str) -> str:
    """从 prediction 末尾提取最后出现的 Yes 或 No（task_36 专用，大小写不敏感）"""
    matches = re.findall(r'\b(Yes|No)\b', pred, re.IGNORECASE)
    if not matches:
        return ""
    last = matches[-1]
    return last[0].upper() + last[1:].lower()  # 标准化为 Yes / No


def extract_bracket_block(pred: str) -> str:
    """提取末尾最后一个 [...] 块（BFCL 专用）"""
    matches = re.findall(r'\[.+?\]', pred, re.DOTALL)
    return matches[-1] if matches else pred


# ══════════════════════════════════════════════════════════════════════════════
# 评测逻辑
# ══════════════════════════════════════════════════════════════════════════════

def reeval_task34(details_path: Path) -> tuple[list[dict], float]:
    """重新评测 task_34，返回 (updated_rows, new_accuracy)"""
    rows = []
    with open(details_path) as f:
        for line in f:
            rows.append(json.loads(line))

    correct = 0
    for row in rows:
        pred_raw = row["prediction"]["prediction"]
        gold = str(row["prediction"]["gold"]).strip()
        extracted = extract_digit_0_4(pred_raw)
        match = (extracted == gold)
        row["eval_res"] = match
        row["eval_details"] = f"extracted={repr(extracted)}"
        if match:
            correct += 1

    accuracy = round(correct / len(rows) * 100, 2) if rows else 0.0
    return rows, accuracy


def reeval_task36(details_path: Path) -> tuple[list[dict], float]:
    """重新评测 task_36，返回 (updated_rows, new_accuracy)"""
    rows = []
    with open(details_path) as f:
        for line in f:
            rows.append(json.loads(line))

    correct = 0
    for row in rows:
        pred_raw = row["prediction"]["prediction"]
        gold = str(row["prediction"]["gold"]).strip()
        extracted = extract_yes_no(pred_raw)
        match = (extracted == gold)
        row["eval_res"] = match
        row["eval_details"] = f"extracted={repr(extracted)}"
        if match:
            correct += 1

    accuracy = round(correct / len(rows) * 100, 2) if rows else 0.0
    return rows, accuracy


def reeval_bfcl(details_path: Path, bfcl_data_dir: Path) -> tuple[list[dict], float]:
    """重新评测 BFCL，返回 (updated_rows, new_accuracy)"""
    if not BFCL_AVAILABLE:
        print("❌ bfcl_eval 不可用，跳过 BFCL", file=sys.stderr)
        return [], 0.0

    # 加载原始 BFCL 数据集（获取 function 定义）
    bfcl_simple_path = bfcl_data_dir / "BFCL_v3_simple.json"
    bfcl_answer_path = bfcl_data_dir / "possible_answer" / "BFCL_v3_simple.json"

    func_map = {}   # id → function spec list
    answer_map = {}  # id → possible_answer list

    with open(bfcl_simple_path) as f:
        for line in f:
            item = json.loads(line)
            func_map[item["id"]] = item.get("function", [])

    with open(bfcl_answer_path) as f:
        for line in f:
            item = json.loads(line)
            answer_map[item["id"]] = item.get("ground_truth", [])

    rows = []
    with open(details_path) as f:
        for line in f:
            rows.append(json.loads(line))

    correct = 0
    for row in rows:
        item_id = row["prediction"]["id"]
        pred_raw = row["prediction"]["prediction"]

        # 提取 [...] 块
        extracted = extract_bracket_block(pred_raw)

        # 尝试解析 AST
        try:
            decoded = default_decode_ast_prompting(extracted, "Python")
        except Exception as e:
            row["eval_res"] = False
            row["eval_details"] = f"decode_error={str(e)}"
            continue

        # 检查格式
        if not is_function_calling_format_output(decoded):
            row["eval_res"] = False
            row["eval_details"] = "wrong_format"
            continue

        # 获取 function spec 和 gold
        func_id = f"simple_{item_id}"
        prompt_item = func_map.get(func_id, [])
        possible_answer = answer_map.get(func_id, [])

        if not prompt_item or not possible_answer:
            row["eval_res"] = False
            row["eval_details"] = f"missing_spec_or_gold for id={func_id}"
            continue

        # 调用 ast_checker
        try:
            checker = ast_checker(
                prompt_item, decoded, possible_answer, "Python", "simple", "telechat-36b"
            )
            is_correct = checker.get("valid", False)
            errors = checker.get("error", [])
            detail = errors[0] if errors else "checker_failed"
        except Exception as e:
            is_correct = False
            detail = f"checker_error={str(e)}"

        row["eval_res"] = is_correct
        if is_correct:
            correct += 1
            row["eval_details"] = f"extracted={repr(extracted)}"
        else:
            row["eval_details"] = detail

    # BFCL 得分乘以 100 后保留一位小数（与原始格式一致）
    accuracy = round(correct / len(rows) * 100, 1) if rows else 0.0
    return rows, accuracy


# ══════════════════════════════════════════════════════════════════════════════
# 写回文件
# ══════════════════════════════════════════════════════════════════════════════

def write_details_jsonl(path: Path, rows: list[dict]):
    with open(path, "w", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    print(f"  ✅ 写回 details: {path}")


def write_score_json(path: Path, accuracy: float):
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"accuracy": accuracy, "type": "GEN"}, f, indent=4, ensure_ascii=False)
    print(f"  ✅ 写回 score:   {path}  →  accuracy={accuracy}")


def update_report_json(report_path: Path, updates: dict[str, float]):
    """更新 report.json 中对应任务的 accuracy，并重新计算 avg"""
    with open(report_path) as f:
        report = json.load(f)

    for task_entry in report.get("tasks", []):
        task_name = task_entry.get("task", "")
        if task_name in updates:
            old = task_entry["accuracy"]
            task_entry["accuracy"] = updates[task_name]
            print(f"  ✅ report.json  {task_name}: {old} → {updates[task_name]}")

    # 重新计算 avg_accuracy（所有 tasks 的平均）
    all_acc = [t["accuracy"] for t in report.get("tasks", []) if t.get("accuracy") is not None]
    if all_acc:
        report["avg_accuracy"] = round(sum(all_acc) / len(all_acc), 4)

    # 分别更新 custom / generic avg
    custom_tasks = [t for t in report["tasks"] if t.get("type") == "custom" and t.get("accuracy") is not None]
    generic_tasks = [t for t in report["tasks"] if t.get("type") == "generic" and t.get("accuracy") is not None]
    if custom_tasks:
        report["summary"]["custom"]["avg_accuracy"] = round(
            sum(t["accuracy"] for t in custom_tasks) / len(custom_tasks), 2
        )
    if generic_tasks:
        report["summary"]["generic"]["avg_accuracy"] = round(
            sum(t["accuracy"] for t in generic_tasks) / len(generic_tasks), 2
        )

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=4, ensure_ascii=False)
    print(f"  ✅ report.json 更新完成，avg_accuracy={report['avg_accuracy']}")


# ══════════════════════════════════════════════════════════════════════════════
# 主流程
# ══════════════════════════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(description="针对 telechat-36b 重新评测 3 个任务")
    parser.add_argument("--fmt-dir", required=True, help="fmt 目录，如 /Users/jia/windowsShare/fmt0416_common")
    parser.add_argument("--model", default="telechat-36b", help="模型目录名（默认 telechat-36b）")
    parser.add_argument("--eval-version", default="eval_init", help="评测版本（默认 eval_init）")
    parser.add_argument("--bfcl-data-dir", default=None, help="BFCL 数据集目录（默认自动推断）")
    args = parser.parse_args()

    fmt_dir = Path(args.fmt_dir)
    model_dir = fmt_dir / args.model
    eval_dir = model_dir / args.eval_version
    results_dir = eval_dir / "results"
    report_path = eval_dir / "report.json"

    # 自动推断 BFCL 数据集目录（相对于本脚本所在位置）
    script_dir = Path(__file__).parent.parent  # benchmark/
    bfcl_data_dir = Path(args.bfcl_data_dir) if args.bfcl_data_dir else script_dir / "data" / "BFCL"

    print(f"📂 模型目录: {model_dir}")
    print(f"📂 BFCL数据: {bfcl_data_dir}")
    print()

    score_updates = {}  # task_name → new_accuracy

    # ── task_34 ──────────────────────────────────────────────────────────────
    print("=== task_34 (政企-意图网关) ===")
    task34_details = results_dir / "task_34_suite" / "task_34_details.jsonl"
    task34_score   = results_dir / "task_34_suite" / "task_34.json"
    rows34, acc34 = reeval_task34(task34_details)
    print(f"  正确率: {acc34}%  ({sum(r['eval_res'] for r in rows34)}/{len(rows34)})")
    write_details_jsonl(task34_details, rows34)
    write_score_json(task34_score, acc34)
    score_updates["task_34"] = acc34
    print()

    # ── task_36 ──────────────────────────────────────────────────────────────
    print("=== task_36 (安全管理-告警研判) ===")
    task36_details = results_dir / "task_36_suite" / "task_36_details.jsonl"
    task36_score   = results_dir / "task_36_suite" / "task_36.json"
    rows36, acc36 = reeval_task36(task36_details)
    print(f"  正确率: {acc36}%  ({sum(r['eval_res'] for r in rows36)}/{len(rows36)})")
    write_details_jsonl(task36_details, rows36)
    write_score_json(task36_score, acc36)
    score_updates["task_36"] = acc36
    print()

    # ── BFCL ─────────────────────────────────────────────────────────────────
    print("=== BFCL v3-单轮任务子集 ===")
    bfcl_details = results_dir / "BFCL_gen_simple" / "BFCL-v3-simple_details.jsonl"
    bfcl_score   = results_dir / "BFCL_gen_simple" / "BFCL-v3-simple.json"
    rows_bfcl, acc_bfcl = reeval_bfcl(bfcl_details, bfcl_data_dir)
    if rows_bfcl:
        print(f"  正确率: {acc_bfcl}%  ({sum(r['eval_res'] for r in rows_bfcl)}/{len(rows_bfcl)})")
        write_details_jsonl(bfcl_details, rows_bfcl)
        write_score_json(bfcl_score, acc_bfcl)
        score_updates["BFCL_gen_simple"] = acc_bfcl
    print()

    # ── 更新 report.json ─────────────────────────────────────────────────────
    print("=== 更新 report.json ===")
    update_report_json(report_path, score_updates)
    print()
    print("🎉 重评测完成！")
    print(f"   task_34:       {acc34}%")
    print(f"   task_36:       {acc36}%")
    if rows_bfcl:
        print(f"   BFCL-v3-simple: {acc_bfcl}%")


if __name__ == "__main__":
    main()
