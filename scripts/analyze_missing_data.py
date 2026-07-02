#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_missing_data.py - 评测数据缺失分析与可视化

生成：
1. 缺失矩阵热力图（任务 × 模型）
2. 按模型/任务的缺失分布柱状图
3. qwen3_235b_think 错误类型饼图
4. 各任务缺失率对比图

用法：
    python scripts/analyze_missing_data.py
"""

import json
import os
import glob
from collections import Counter, defaultdict
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import numpy as np
import pandas as pd

# ── 字体设置 ──────────────────────────────────────────────────────────────
# macOS 中文字体
for font_name in ["PingFang SC", "Heiti SC", "STHeiti", "Arial Unicode MS"]:
    matches = [f for f in fm.fontManager.ttflist if font_name in f.name]
    if matches:
        plt.rcParams["font.sans-serif"] = [font_name] + plt.rcParams["font.sans-serif"]
        break
plt.rcParams["axes.unicode_minus"] = False

DATA_DIR = Path(__file__).resolve().parent.parent / "outputs" / "newfmt_2_aggregated_reports_20260402_103126"
RAW_DIR = Path(os.path.expanduser("~/windowsShare/newfmt_2"))
OUT_DIR = Path(__file__).resolve().parent.parent / "outputs" / "missing_data_analysis"
OUT_DIR.mkdir(parents=True, exist_ok=True)


def is_missing(val) -> bool:
    if val is None:
        return True
    s = str(val).strip()
    return s == "" or s.lower() in ("null", "nan") or len(s) < 4


def check_xlsx(xlsx_path: Path) -> dict:
    try:
        df = pd.read_excel(xlsx_path)
    except Exception as e:
        return {"error": str(e), "total": 0, "missing_count": 0}
    missing = 0
    for _, row in df.iterrows():
        for col in ("origin_prompt", "prediction"):
            if col in df.columns and is_missing(row.get(col)):
                missing += 1
                break
    return {"total": len(df), "missing_count": missing}


def scan_and_check():
    """扫描并检查所有 xlsx 文件"""
    items = []
    for task_dir in sorted(DATA_DIR.iterdir()):
        if not task_dir.is_dir():
            continue
        for model_dir in sorted(task_dir.iterdir()):
            if not model_dir.is_dir():
                continue
            for xlsx in model_dir.glob("*_details.xlsx"):
                items.append((task_dir.name, model_dir.name, xlsx))

    results = []
    with ThreadPoolExecutor(max_workers=12) as executor:
        futures = {executor.submit(check_xlsx, x): (t, m, x) for t, m, x in items}
        for f in as_completed(futures):
            task, model, xlsx = futures[f]
            res = f.result()
            results.append((task, model, res))
    return results


def analyze_errors():
    """分析 qwen3_235b_think 的 failed jsonl"""
    base = RAW_DIR / "qwen3_235b_think"
    failed_files = glob.glob(str(base / "details/*/predictions/local_qwen/*_failed.jsonl"))
    error_counter = Counter()
    suite_errors = defaultdict(Counter)

    for fp in failed_files:
        suite = os.path.basename(fp).replace("_failed.jsonl", "")
        with open(fp) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                obj = json.loads(line)
                err = obj.get("error_info", "unknown")
                error_counter[err] += 1
                suite_errors[suite][err] += 1

    return error_counter, suite_errors


def build_matrix(results):
    """构建缺失矩阵 DataFrame"""
    by_task = defaultdict(lambda: defaultdict(lambda: {"total": 0, "missing": 0}))
    for task, model, res in results:
        by_task[task][model]["total"] += res.get("total", 0)
        by_task[task][model]["missing"] += res.get("missing_count", 0)

    all_tasks = sorted(by_task.keys())
    all_models = sorted({m for t in by_task.values() for m in t})

    # 缺失数矩阵
    missing_matrix = pd.DataFrame(index=all_tasks, columns=all_models, dtype=float)
    # 缺失率矩阵
    rate_matrix = pd.DataFrame(index=all_tasks, columns=all_models, dtype=float)

    for task in all_tasks:
        for model in all_models:
            if model in by_task[task]:
                d = by_task[task][model]
                missing_matrix.loc[task, model] = d["missing"]
                rate_matrix.loc[task, model] = d["missing"] / d["total"] * 100 if d["total"] > 0 else 0
            else:
                missing_matrix.loc[task, model] = np.nan
                rate_matrix.loc[task, model] = np.nan

    return missing_matrix, rate_matrix


def plot_heatmap(rate_matrix: pd.DataFrame, missing_matrix: pd.DataFrame):
    """缺失率热力图"""
    fig, ax = plt.subplots(figsize=(16, 12))

    data = rate_matrix.astype(float).values
    mask = np.isnan(data)

    im = ax.imshow(data, cmap="YlOrRd", aspect="auto", vmin=0, vmax=min(data[~mask].max() * 1.1, 100) if not mask.all() else 100)

    # 标注数值
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            if mask[i, j]:
                ax.text(j, i, "-", ha="center", va="center", fontsize=7, color="gray")
            elif data[i, j] == 0:
                ax.text(j, i, "0", ha="center", va="center", fontsize=7, color="green")
            else:
                mc = int(missing_matrix.iloc[i, j])
                ax.text(j, i, f"{data[i,j]:.1f}%\n({mc})", ha="center", va="center", fontsize=6,
                        color="white" if data[i, j] > 30 else "black")

    ax.set_xticks(range(len(rate_matrix.columns)))
    ax.set_xticklabels(rate_matrix.columns, rotation=45, ha="right", fontsize=8)
    ax.set_yticks(range(len(rate_matrix.index)))
    ax.set_yticklabels(rate_matrix.index, fontsize=8)

    plt.colorbar(im, ax=ax, label="缺失率 (%)", shrink=0.8)
    ax.set_title("评测数据缺失率热力图（任务 × 模型）", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "heatmap_missing_rate.png", dpi=150)
    plt.close()
    print(f"  -> {OUT_DIR / 'heatmap_missing_rate.png'}")


def plot_by_model(results):
    """按模型汇总缺失柱状图"""
    by_model = defaultdict(lambda: {"total": 0, "missing": 0})
    for task, model, res in results:
        by_model[model]["total"] += res.get("total", 0)
        by_model[model]["missing"] += res.get("missing_count", 0)

    models = sorted(by_model.keys())
    totals = [by_model[m]["total"] for m in models]
    missings = [by_model[m]["missing"] for m in models]
    rates = [m / t * 100 if t > 0 else 0 for m, t in zip(missings, totals)]

    fig, ax1 = plt.subplots(figsize=(12, 6))
    x = range(len(models))
    bars = ax1.bar(x, missings, color="#e74c3c", alpha=0.8, label="缺失行数")
    ax1.set_ylabel("缺失行数", color="#e74c3c")
    ax1.set_xticks(x)
    ax1.set_xticklabels(models, rotation=30, ha="right", fontsize=9)

    ax2 = ax1.twinx()
    ax2.plot(x, rates, "o-", color="#2980b9", linewidth=2, markersize=8, label="缺失率")
    ax2.set_ylabel("缺失率 (%)", color="#2980b9")

    for i, (b, r) in enumerate(zip(bars, rates)):
        ax1.text(b.get_x() + b.get_width() / 2, b.get_height(), str(missings[i]),
                 ha="center", va="bottom", fontsize=8)
        ax2.text(i, r + 0.3, f"{r:.1f}%", ha="center", va="bottom", fontsize=8, color="#2980b9")

    ax1.set_title("各模型数据缺失分布", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "bar_by_model.png", dpi=150)
    plt.close()
    print(f"  -> {OUT_DIR / 'bar_by_model.png'}")


def plot_by_task(results):
    """按任务汇总缺失柱状图（只显示有缺失的任务）"""
    by_task = defaultdict(lambda: {"total": 0, "missing": 0})
    for task, model, res in results:
        by_task[task]["total"] += res.get("total", 0)
        by_task[task]["missing"] += res.get("missing_count", 0)

    # 过滤有缺失的
    tasks = sorted([t for t in by_task if by_task[t]["missing"] > 0],
                   key=lambda t: by_task[t]["missing"], reverse=True)
    missings = [by_task[t]["missing"] for t in tasks]
    rates = [by_task[t]["missing"] / by_task[t]["total"] * 100 for t in tasks]

    fig, ax = plt.subplots(figsize=(14, 7))
    bars = ax.barh(range(len(tasks)), missings, color="#e67e22", alpha=0.85)
    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels(tasks, fontsize=9)
    ax.invert_yaxis()

    for i, (b, r) in enumerate(zip(bars, rates)):
        ax.text(b.get_width() + 5, b.get_y() + b.get_height() / 2,
                f"{missings[i]} ({r:.1f}%)", va="center", fontsize=8)

    ax.set_xlabel("缺失行数")
    ax.set_title("各任务数据缺失排名（仅显示有缺失的任务）", fontsize=14, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "bar_by_task.png", dpi=150)
    plt.close()
    print(f"  -> {OUT_DIR / 'bar_by_task.png'}")


def plot_error_types(error_counter):
    """qwen3_235b_think 错误类型饼图"""
    labels = list(error_counter.keys())
    values = list(error_counter.values())
    colors = ["#e74c3c", "#f39c12"]

    fig, ax = plt.subplots(figsize=(8, 6))
    wedges, texts, autotexts = ax.pie(
        values, labels=labels, autopct="%1.1f%%", colors=colors[:len(labels)],
        startangle=90, textprops={"fontsize": 11}
    )
    ax.set_title("qwen3_235b_think 推理失败错误类型分布\n（共 {} 次失败）".format(sum(values)),
                 fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "pie_error_types.png", dpi=150)
    plt.close()
    print(f"  -> {OUT_DIR / 'pie_error_types.png'}")


def plot_235b_task_failures(suite_errors):
    """qwen3_235b_think 各子任务失败数量 top 15"""
    task_totals = {suite: sum(cnt.values()) for suite, cnt in suite_errors.items()}
    top = sorted(task_totals.items(), key=lambda x: x[1], reverse=True)[:15]

    tasks = [t[0] for t in top]
    counts = [t[1] for t in top]

    fig, ax = plt.subplots(figsize=(12, 6))
    bars = ax.barh(range(len(tasks)), counts, color="#c0392b", alpha=0.85)
    ax.set_yticks(range(len(tasks)))
    ax.set_yticklabels(tasks, fontsize=9)
    ax.invert_yaxis()

    for i, b in enumerate(bars):
        ax.text(b.get_width() + 2, b.get_y() + b.get_height() / 2,
                str(counts[i]), va="center", fontsize=9)

    ax.set_xlabel("失败次数")
    ax.set_title("qwen3_235b_think 推理失败次数 Top 15 子任务", fontsize=13, fontweight="bold")
    fig.tight_layout()
    fig.savefig(OUT_DIR / "bar_235b_top_failures.png", dpi=150)
    plt.close()
    print(f"  -> {OUT_DIR / 'bar_235b_top_failures.png'}")


def main():
    print("1. 扫描并检查所有 xlsx 文件...")
    results = scan_and_check()
    print(f"   共 {len(results)} 个文件")

    print("2. 构建缺失矩阵...")
    missing_matrix, rate_matrix = build_matrix(results)

    print("3. 分析 qwen3_235b_think 错误日志...")
    error_counter, suite_errors = analyze_errors()

    print("4. 生成可视化图表...")
    plot_heatmap(rate_matrix, missing_matrix)
    plot_by_model(results)
    plot_by_task(results)
    plot_error_types(error_counter)
    plot_235b_task_failures(suite_errors)

    # 保存矩阵 CSV
    missing_matrix.to_csv(OUT_DIR / "missing_matrix.csv")
    rate_matrix.to_csv(OUT_DIR / "missing_rate_matrix.csv")
    print(f"5. CSV 已保存到 {OUT_DIR}")

    print(f"\n所有分析输出: {OUT_DIR}")


if __name__ == "__main__":
    main()
