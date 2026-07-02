#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
check_eval_data.py - 检测评测数据缺失情况

结构：data_dir/{task}/{model}/{xxx}_details.xlsx
缺失条件：origin_prompt 或 prediction 列为空/null/长度<4

用法：
    python check_eval_data.py --data-dir /path/to/aggregated_reports_xxx
    python check_eval_data.py --data-dir /path/to/... --workers 16
"""

import argparse
import os
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import pandas as pd


def is_missing(val) -> bool:
    """判断一个值是否缺失"""
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s.lower() == "null" or s.lower() == "nan"


def check_xlsx(xlsx_path: Path) -> dict:
    """
    检查单个 xlsx 文件，返回缺失行信息。
    返回：{total, missing_count, missing_rows: [{row_idx, missing_cols}]}
    """
    try:
        df = pd.read_excel(xlsx_path)
    except Exception as e:
        return {"error": str(e), "total": 0, "missing_count": 0, "missing_rows": []}

    missing_rows = []
    for idx, row in df.iterrows():
        missing_cols = []
        for col in ("origin_prompt", "prediction"):
            if col in df.columns and is_missing(row.get(col)):
                missing_cols.append(col)
        if missing_cols:
            missing_rows.append({"row_idx": idx, "missing_cols": missing_cols})

    return {
        "total": len(df),
        "missing_count": len(missing_rows),
        "missing_rows": missing_rows,
    }


def scan_data_dir(data_dir: Path):
    """
    扫描 data_dir/{task}/{model}/*.xlsx，返回任务列表。
    结果：[(task, model, xlsx_path), ...]
    """
    items = []
    for task_dir in sorted(data_dir.iterdir()):
        if not task_dir.is_dir():
            continue
        for model_dir in sorted(task_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            for xlsx in model_dir.glob("*_details.xlsx"):
                items.append((task_dir.name, model_dir.name, xlsx))
    return items


def run_checks(items: list, workers: int) -> list:
    """并发检查所有 xlsx，返回 [(task, model, xlsx_path, result), ...]"""
    results = []
    with ThreadPoolExecutor(max_workers=workers) as executor:
        future_to_item = {
            executor.submit(check_xlsx, xlsx): (task, model, xlsx)
            for task, model, xlsx in items
        }
        for future in as_completed(future_to_item):
            task, model, xlsx = future_to_item[future]
            result = future.result()
            results.append((task, model, xlsx, result))
    return results


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def report(results: list):
    # 整理数据结构
    # by_task[task][model] = [result, ...]
    by_task = defaultdict(lambda: defaultdict(list))
    by_model = defaultdict(lambda: defaultdict(list))

    total_files = len(results)
    total_missing_files = 0
    total_missing_rows = 0
    total_rows = 0

    for task, model, xlsx, res in results:
        by_task[task][model].append((xlsx, res))
        by_model[model][task].append((xlsx, res))
        total_rows += res.get("total", 0)
        mc = res.get("missing_count", 0)
        total_missing_rows += mc
        if mc > 0 or "error" in res:
            total_missing_files += 1

    # ── 总览 ─────────────────────────────────────────────────────────────────
    print_section("总览")
    print(f"  文件总数：{total_files}")
    print(f"  行总数：{total_rows}")
    print(f"  有缺失的文件数：{total_missing_files}")
    print(f"  缺失行总数：{total_missing_rows}")

    # ── 按任务维度 ────────────────────────────────────────────────────────────
    print_section("按【任务】维度 — 各任务的缺失情况")
    for task in sorted(by_task):
        models = by_task[task]
        task_missing = sum(
            res.get("missing_count", 0)
            for model_results in models.values()
            for _, res in model_results
        )
        task_total = sum(
            res.get("total", 0)
            for model_results in models.values()
            for _, res in model_results
        )
        flag = " ⚠️" if task_missing > 0 else " ✅"
        print(f"\n  [{task}]{flag}  总行数={task_total}  缺失行={task_missing}")
        for model in sorted(models):
            model_missing = sum(r.get("missing_count", 0) for _, r in models[model])
            model_total = sum(r.get("total", 0) for _, r in models[model])
            if model_missing > 0:
                print(f"    ├─ {model}: {model_missing}/{model_total} 行缺失")
                for xlsx, res in models[model]:
                    if res.get("missing_count", 0) > 0:
                        print(f"       └─ {xlsx.name}: {res['missing_count']} 行")
                        for mr in res["missing_rows"][:5]:
                            print(f"          row {mr['row_idx']}: 缺失列={mr['missing_cols']}")
                        if len(res["missing_rows"]) > 5:
                            print(f"          ... 共 {len(res['missing_rows'])} 行")
            elif "error" in res.get("", {}):
                print(f"    ├─ {model}: ❌ 读取失败")

    # ── 按模型维度 ────────────────────────────────────────────────────────────
    print_section("按【模型】维度 — 各模型的缺失情况")
    for model in sorted(by_model):
        tasks = by_model[model]
        model_missing = sum(
            res.get("missing_count", 0)
            for task_results in tasks.values()
            for _, res in task_results
        )
        model_total = sum(
            res.get("total", 0)
            for task_results in tasks.values()
            for _, res in task_results
        )
        flag = " ⚠️" if model_missing > 0 else " ✅"
        print(f"\n  [{model}]{flag}  总行数={model_total}  缺失行={model_missing}")
        for task in sorted(tasks):
            task_missing = sum(r.get("missing_count", 0) for _, r in tasks[task])
            task_total = sum(r.get("total", 0) for _, r in tasks[task])
            if task_missing > 0:
                print(f"    ├─ {task}: {task_missing}/{task_total} 行缺失")
                for xlsx, res in tasks[task]:
                    if res.get("missing_count", 0) > 0:
                        print(f"       └─ {xlsx.name}: {res['missing_count']} 行")

    # ── 缺失矩阵（任务 x 模型）────────────────────────────────────────────────
    print_section("缺失矩阵（任务 × 模型，显示缺失行数，0 表示无缺失，- 表示无数据）")
    all_tasks = sorted(by_task.keys())
    all_models = sorted(by_model.keys())

    # 构建矩阵
    matrix = {}
    for task in all_tasks:
        matrix[task] = {}
        for model in all_models:
            if model in by_task[task]:
                mc = sum(r.get("missing_count", 0) for _, r in by_task[task][model])
                matrix[task][model] = mc
            else:
                matrix[task][model] = None  # 无数据

    # 计算列宽
    col_w = max(len(m) for m in all_models) + 2 if all_models else 10
    task_w = max(len(t) for t in all_tasks) + 2 if all_tasks else 20
    task_w = max(task_w, 20)

    header = f"{'任务':<{task_w}}" + "".join(f"{m:>{col_w}}" for m in all_models)
    print(f"\n  {header}")
    print(f"  {'-' * len(header)}")
    for task in all_tasks:
        row_str = f"{task:<{task_w}}"
        for model in all_models:
            val = matrix[task][model]
            if val is None:
                cell = "-"
            elif val == 0:
                cell = "0"
            else:
                cell = str(val)
            row_str += f"{cell:>{col_w}}"
        print(f"  {row_str}")


def main():
    parser = argparse.ArgumentParser(description="检测评测数据缺失情况")
    parser.add_argument(
        "--data-dir",
        required=True,
        help="聚合报告目录，即 aggregate_eval_reports.py 的输出目录（内含 task/model/ 结构）",
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=8,
        help="并发线程数（默认 8）",
    )
    args = parser.parse_args()

    data_dir = Path(args.data_dir)
    if not data_dir.exists():
        print(f"❌ 目录不存在：{data_dir}")
        return

    print(f"扫描目录：{data_dir}")
    items = scan_data_dir(data_dir)
    if not items:
        print("❌ 未找到任何 *_details.xlsx 文件")
        return

    print(f"找到 {len(items)} 个 xlsx 文件，使用 {args.workers} 线程并发检测...")
    results = run_checks(items, args.workers)
    report(results)


if __name__ == "__main__":
    main()
