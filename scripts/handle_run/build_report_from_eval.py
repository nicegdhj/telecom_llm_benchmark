#!/usr/bin/env python3
"""从已有的 eval_{version}/{summary,results}/ 反向生成 report.md / report.json。

用于合并补跑结果后重新出总报告。
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

_EXCLUDED_METRIC_PREFIXES = ("parse_success_rate", "field_")


def parse_summary(summary_dir: Path):
    acc = None
    for p in summary_dir.glob("summary_*.txt"):
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        csv_start = -1
        for idx, line in enumerate(lines):
            if line.strip() == "csv format":
                csv_start = idx
                break
        if csv_start == -1:
            continue
        total, n = 0.0, 0
        for i in range(csv_start + 3, len(lines)):
            line = lines[i]
            if line.startswith("$") or not line.strip():
                break
            parts = line.strip().split(",")
            if len(parts) >= 5 and not parts[2].strip().startswith(_EXCLUDED_METRIC_PREFIXES):
                try:
                    total += float(parts[-1])
                    n += 1
                except (ValueError, TypeError):
                    pass
        if n > 0:
            acc = round(total / n, 2)
    return acc


def count_samples(results_dir: Path):
    files = list(results_dir.glob("**/*_details.jsonl"))
    if not files:
        return None
    total = 0
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                total += sum(1 for _ in fh)
        except Exception:
            pass
    return total or None


def detect_eval_type(suite: str, configs_dir: Path):
    for py in configs_dir.rglob(f"{suite}.py"):
        try:
            if "LLMJudgeEvaluator" in py.read_text(encoding="utf-8"):
                return "llm"
        except Exception:
            pass
    return "rule"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model-dir", required=True,
                    help="如 /Users/jia/windowsShare/formal0416/pt_v_0_2")
    ap.add_argument("--eval-version", default="eval_init")
    ap.add_argument("--infer-task", default=None,
                    help="默认取 model-dir 的名称")
    ap.add_argument("--configs-dir", default=None,
                    help="ais_bench configs 目录，用于识别 LLM 评测")
    args = ap.parse_args()

    model_dir = Path(args.model_dir)
    eval_dir = model_dir / args.eval_version
    meta_path = model_dir / "infer_meta.json"
    if not meta_path.exists():
        print(f"❌ 缺少 {meta_path}")
        sys.exit(1)
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    model_name = meta.get("model_name", model_dir.name)
    infer_task = args.infer_task or model_dir.name

    configs_dir = Path(args.configs_dir) if args.configs_dir else \
        Path(__file__).resolve().parents[2] / "ais_bench" / "benchmark" / "configs"

    results = []
    for suite, info in meta["tasks"].items():
        s_summary = eval_dir / "summary" / suite
        s_results = eval_dir / "results" / suite
        eval_type = detect_eval_type(suite, configs_dir)
        acc = parse_summary(s_summary) if s_summary.exists() else None
        n_samples = count_samples(s_results) if s_results.exists() else None
        status = "success" if acc is not None else "failed"
        results.append({
            "task": info.get("task_name", suite),
            "suite": suite,
            "type": info.get("type"),
            "eval_type": eval_type,
            "status": status,
            "accuracy": acc,
            "num_samples": n_samples or info.get("num_samples"),
            "duration_sec": info.get("duration_sec", 0) or 0,
            "returncode": 0 if status == "success" else -1,
        })

    accs = [r["accuracy"] for r in results if r["accuracy"] is not None]
    avg = sum(accs) / len(accs) if accs else 0.0

    summary_stats = {
        "custom":  {"count": 0, "total_duration_sec": 0.0, "accuracies": []},
        "generic": {"count": 0, "total_duration_sec": 0.0, "accuracies": []},
    }
    for r in results:
        t = r["type"] if r["type"] in summary_stats else "custom"
        summary_stats[t]["count"] += 1
        summary_stats[t]["total_duration_sec"] += r["duration_sec"]
        if r["accuracy"] is not None:
            summary_stats[t]["accuracies"].append(r["accuracy"])
    for t in summary_stats:
        accs_ = summary_stats[t].pop("accuracies")
        summary_stats[t]["avg_accuracy"] = round(sum(accs_) / len(accs_), 2) if accs_ else 0.0
        summary_stats[t]["total_duration_sec"] = round(summary_stats[t]["total_duration_sec"], 1)

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# 评测报告", "",
        f"- **Infer Task**: `{infer_task}`",
        f"- **Eval Version**: `{args.eval_version}`",
        f"- **模型**: `{model_name}`",
        f"- **时间**: {now}",
        f"- **综合准确率**: {avg:.2f}%",
        "",
        "## 统计摘要", "",
        "| 任务类型 | 任务数量 | 总耗时 (秒) | 平均准确率 |",
        "|----------|----------|-------------|------------|",
        f"| 自定义 (Custom) | {summary_stats['custom']['count']} | {summary_stats['custom']['total_duration_sec']} | {summary_stats['custom']['avg_accuracy']}% |",
        f"| 通用 (Generic)  | {summary_stats['generic']['count']} | {summary_stats['generic']['total_duration_sec']} | {summary_stats['generic']['avg_accuracy']}% |",
        "",
        "## 各任务明细", "",
        "| 任务 | 类型 | 评估方式 | 状态 | 耗时(秒) | 数据量 | 准确率 |",
        "|------|------|----------|------|----------|--------|--------|",
    ]
    for r in results:
        icon = "✅" if r["status"] == "success" else "❌"
        acc_s = f"{r['accuracy']:.2f}%" if r["accuracy"] is not None else "-"
        n_s = str(r["num_samples"]) if r["num_samples"] is not None else "-"
        lines.append(
            f"| {r['task']} | {r['type']} | {r['eval_type']} | {icon} {r['status']} | "
            f"{r['duration_sec']} | {n_s} | {acc_s} |"
        )

    (eval_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    (eval_dir / "report.json").write_text(
        json.dumps({
            "infer_task": infer_task,
            "eval_version": args.eval_version,
            "model": model_name,
            "timestamp": now,
            "avg_accuracy": round(avg, 4),
            "summary": summary_stats,
            "tasks": results,
        }, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"✅ 已生成:\n   {eval_dir / 'report.md'}\n   {eval_dir / 'report.json'}")
    print(f"   综合准确率: {avg:.2f}%   ({len(accs)}/{len(results)} 任务有分)")


if __name__ == "__main__":
    main()
