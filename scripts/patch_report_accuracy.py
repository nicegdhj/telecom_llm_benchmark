#!/usr/bin/env python3
"""补丁脚本：从 summary 文件重新解析 accuracy 回填到 report.json。

用法:
    python patch_report_accuracy.py <eval_dir> [<eval_dir2> ...]
    python patch_report_accuracy.py ~/Desktop/fmt_all/fmt_exp0318/*/eval_1

修复问题：根据 summary 中的主评分指标重新计算 report.json accuracy。
既可回填 null，也可修正误将辅助指标混入平均值的已有错误结果。
"""

import json
import sys
from pathlib import Path

_EXCLUDED_METRIC_PREFIXES = (
    "parse_success_rate",
    "field_",
    "hallucination_rate",
)


def parse_accuracy_from_summary(eval_dir: Path, suite: str) -> float | None:
    """从 eval_dir/summary/<suite>/summary_*.txt 解析准确率。"""
    summary_dir = eval_dir / "summary" / suite
    if not summary_dir.exists():
        return None

    for summary_path in summary_dir.glob("summary_*.txt"):
        try:
            text = summary_path.read_text(encoding="utf-8")
            lines = text.splitlines()
            csv_start = -1
            for idx, line in enumerate(lines):
                if line.strip() == "csv format":
                    csv_start = idx
                    break

            if csv_start == -1:
                continue

            total_acc = 0.0
            valid_count = 0
            for i in range(csv_start + 3, len(lines)):
                if lines[i].startswith("$") or not lines[i].strip():
                    break
                parts = lines[i].strip().split(",")
                if len(parts) >= 5:
                    metric_name = parts[2].strip()
                    if not metric_name.startswith(_EXCLUDED_METRIC_PREFIXES):
                        try:
                            total_acc += float(parts[-1])
                            valid_count += 1
                        except (ValueError, TypeError):
                            pass

            if valid_count > 0:
                return round(total_acc / valid_count, 2)
        except Exception:
            pass

    return None


def patch_report(eval_dir: Path) -> None:
    report_path = eval_dir / "report.json"
    if not report_path.exists():
        print(f"  跳过：{report_path} 不存在")
        return

    with open(report_path, "r", encoding="utf-8") as f:
        report = json.load(f)

    patched = []
    for task in report.get("tasks", []):
        if task.get("status") != "success":
            continue

        suite = task.get("suite", task.get("task", ""))
        new_acc = parse_accuracy_from_summary(eval_dir, suite)
        old_acc = task.get("accuracy")
        if new_acc is not None and new_acc != old_acc:
            task["accuracy"] = new_acc
            patched.append(f"    {task['task']}: {old_acc} -> {new_acc}")

    if not patched:
        print(f"  无需修复：{report_path}")
        return

    # 重新计算 avg_accuracy 和 summary 中的 avg_accuracy
    all_accs = [t["accuracy"] for t in report["tasks"] if t["accuracy"] is not None]
    report["avg_accuracy"] = round(sum(all_accs) / len(all_accs), 4) if all_accs else 0.0

    for task_type in ("custom", "generic"):
        type_accs = [
            t["accuracy"] for t in report["tasks"]
            if t["accuracy"] is not None and t.get("type") == task_type
        ]
        if task_type in report.get("summary", {}):
            report["summary"][task_type]["avg_accuracy"] = (
                round(sum(type_accs) / len(type_accs), 2) if type_accs else 0.0
            )

    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print(f"  已修复 {report_path}:")
    for line in patched:
        print(line)


def main():
    if len(sys.argv) < 2:
        print(f"用法: {sys.argv[0]} <eval_dir> [<eval_dir2> ...]")
        sys.exit(1)

    for arg in sys.argv[1:]:
        eval_dir = Path(arg)
        print(f"\n处理: {eval_dir}")
        patch_report(eval_dir)


if __name__ == "__main__":
    main()
