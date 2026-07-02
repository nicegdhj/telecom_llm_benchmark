#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_judge.py - 评测专用脚本

基于 eval_entry.py 推理阶段产出的 infer_meta.json，
复用推理结果执行评测，支持版本化管理和按需重跑。

执行策略：
  - 规则型任务：多进程并行（并发数由 SCORE_WORKER_CONCURRENCY 控制）
  - LLM 打分任务：串行执行（打分模型 API 并发由 SCORE_LLM_CONCURRENCY 控制）

用法:
    # 评测所有任务（规则型并行，LLM 型串行）
    python eval_judge.py --infer-task round_1

    # 只评测指定任务，按传入顺序执行
    python eval_judge.py --infer-task round_1 --eval-tasks telequad_gen_0_shot task_1_suite

    # 指定评测版本号
    python eval_judge.py --infer-task round_1 --eval-version v2_fix_weight
"""

import argparse
import gc
import json
import os
import shutil
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).parent.resolve()
load_dotenv(ROOT / ".env", override=False)

CONFIGS_DIR = ROOT / "ais_bench" / "benchmark" / "configs" / "datasets"


# ── 参数解析 ────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="评测专用脚本：基于已有推理结果执行评测",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--infer-task",
        required=True,
        help="推理批次标识，对应 outputs/{infer-task}/infer_meta.json",
    )
    parser.add_argument(
        "--eval-version",
        default=None,
        help="评测版本标识。不传则自动生成 eval_{YYYYMMDD_HHMMSS}",
    )
    parser.add_argument(
        "--eval-tasks",
        nargs="*",
        default=None,
        help="指定要评测的任务（suite 名称），按传入顺序执行。不传则评测所有任务",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "outputs"),
        help="输出根目录（默认 outputs/）",
    )
    parser.add_argument(
        "--score-worker-concurrency",
        type=int,
        default=int(os.environ.get("SCORE_WORKER_CONCURRENCY", "4")),
        help="规则型评测并行进程数（默认读取 SCORE_WORKER_CONCURRENCY，否则 4）",
    )
    parser.add_argument(
        "--task-timeout",
        type=int,
        default=int(os.environ.get("EVAL_TASK_TIMEOUT", "3600")),
        help="单个评测任务最大执行时间（秒），超时强制终止并跳过。默认3600秒",
    )
    parser.add_argument(
        "--skip-llm",
        action="store_true",
        default=False,
        help="跳过 LLM 打分类型的评测任务，只执行规则型评测",
    )
    return parser.parse_args()


# ── LLM 评估器检测 ───────────────────────────────────────────────────
def detect_evaluator_type(suite_name: str) -> str:
    """扫描 suite 配置文件，检测 evaluator 是否需要 LLM 打分模型。

    两级检测：
      1. 配置文件中直接包含 LLMJudgeEvaluator 字符串
      2. 配置文件引用的评测器（如 ExamDynamicEvaluator）内部依赖 LLMJudgeEvaluator

    Returns:
        'llm' 或 'rule'
    """
    for py_file in CONFIGS_DIR.rglob(f"{suite_name}.py"):
        try:
            content = py_file.read_text(encoding="utf-8")
            if "LLMJudgeEvaluator" in content:
                return "llm"
            # 评分器名不直接包含 LLMJudgeEvaluator 但可能内部引用了它
            # 如 ExamDynamicEvaluator
            if "ExamDynamicEvaluator" in content:
                return "llm"
        except Exception:
            pass
    return "rule"


def split_tasks_by_eval_type(suites: list) -> tuple:
    """将任务按评估器类型分组：规则型 和 LLM 型。"""
    rule_tasks = []
    llm_tasks = []
    for suite in suites:
        if detect_evaluator_type(suite) == "llm":
            llm_tasks.append(suite)
        else:
            rule_tasks.append(suite)
    return rule_tasks, llm_tasks


# ── 内存清理（与 eval_entry.py 保持一致） ───────────────────────────
def _cleanup_leaked_shm():
    """清理 /dev/shm 中残留的 Python 共享内存段，防止 OOM。"""
    shm_dir = Path("/dev/shm")
    if not shm_dir.exists():
        return
    cleaned = 0
    for f in shm_dir.iterdir():
        if f.name.startswith(("psm_", "wnsm_")):
            try:
                f.unlink()
                cleaned += 1
            except OSError:
                pass
    if cleaned:
        print(f"   🧹 已清理 {cleaned} 个残留共享内存段")


# ── 单任务评测 ───────────────────────────────────────────────────────
def run_eval_for_task(
    suite: str,
    timestamp: str,
    task_info: dict,
    eval_type: str,
    model_config: str,
    infer_task_dir: Path,
    eval_dir: Path,
    task_timeout: int = 3600,
) -> dict:
    """对单个任务执行评测，搬运结果到 eval_dir。"""

    # ais_bench --mode eval 使用 --work-dir 和 --reuse 定位推理结果
    # work_dir = infer_task_dir/details, reuse = timestamp
    # → 实际 work_dir = infer_task_dir/details/{timestamp}/
    # → 读取 predictions/ ✓
    # → 写入 results/、logs/eval/、summary/ 到同一目录
    details_base = str(infer_task_dir / "details")

    cmd = [
        sys.executable, "-m", "ais_bench.benchmark.cli.main",
        "--mode", "eval",
        "--work-dir", details_base,
        "--reuse", timestamp,
        "--models", model_config,
        "--datasets", suite,
    ]

    # 任务开始前清理残留共享内存，防止前面任务的泄漏累积导致死锁
    _cleanup_leaked_shm()

    start_time = time.time()
    status = "success"
    returncode = 0
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            capture_output=False,
            timeout=task_timeout,
        )
        returncode = proc.returncode
        if returncode != 0:
            status = "failed"
    except subprocess.TimeoutExpired:
        print(f"   ⏰ 任务 {suite} 超时（>{task_timeout}s），强制终止并跳过")
        status = "timeout"
        returncode = -1
    duration = time.time() - start_time

    # 解析评测结果（超时也尝试解析已产出的部分结果）
    work_dir = infer_task_dir / "details" / timestamp
    accuracy, num_samples = _parse_eval_result(work_dir, suite)

    # 搬运 results/、logs/eval/、summary/ 到 eval_dir/{suite}/
    _move_eval_outputs(work_dir, eval_dir, suite)

    # 内存清理
    _cleanup_leaked_shm()
    gc.collect()

    return {
        "task": task_info["task_name"],
        "suite": suite,
        "type": task_info["type"],
        "eval_type": eval_type,
        "status": status,
        "accuracy": accuracy,
        "num_samples": num_samples or task_info.get("num_samples"),
        "duration_sec": round(duration, 1),
        "returncode": returncode,
    }


def _parse_eval_result(work_dir: Path, suite: str) -> tuple:
    """从评测产出中解析准确率和样本数。

    Returns:
        (accuracy: float | None, num_samples: int | None)
    """
    accuracy = None
    num_samples = None

    # 从 summary 解析准确率
    # CSV 格式：dataset,version,metric,mode,score[,score2...]
    # 排除 parse_success_rate、field_* 等辅助指标，只保留主评分指标
    _EXCLUDED_METRIC_PREFIXES = ("parse_success_rate", "field_")
    for summary_path in work_dir.glob("summary/summary_*.txt"):
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
                accuracy = round(total_acc / valid_count, 2)
        except Exception:
            pass

    # 兜底：summary 缺失时，从各子任务结果 JSON 文件恢复得分（简单平均）
    # 适用场景：ais_bench eval 写完各子任务结果后在 summary 阶段挂起被 kill
    if accuracy is None:
        score_files = [
            f for f in (work_dir / "results").glob("**/*.json")
            if not f.name.endswith("_details.json")
        ]
        subtask_scores = []
        for jf in score_files:
            try:
                data = json.loads(jf.read_text(encoding="utf-8"))
                if "error" in data:
                    continue
                score = data.get("accuracy", data.get("score"))
                if isinstance(score, (int, float)):
                    subtask_scores.append(float(score))
            except Exception:
                pass
        if subtask_scores:
            accuracy = round(sum(subtask_scores) / len(subtask_scores), 2)

    # 从 results 的 details.jsonl 统计样本数
    details_files = list((work_dir / "results").glob("**/*_details.jsonl"))
    if details_files:
        try:
            num_samples = sum(
                sum(1 for _ in open(f, "r", encoding="utf-8"))
                for f in details_files
            )
        except Exception:
            pass

    return accuracy, num_samples


def _move_eval_outputs(work_dir: Path, eval_dir: Path, suite: str):
    """将 ais_bench eval 产出从 work_dir 搬运到 eval_dir，按 suite 分目录。

    目标结构：
        eval_dir/
        ├── results/{suite}/    ← 展平 results/{model_config}/ 这一层
        ├── summary/{suite}/    ← summary 文件按 suite 归档
        └── logs/{suite}/       ← 展平 logs/eval/{model_config}/ 这两层
    """
    def _copy_files_flat(src_root: Path, dest_dir: Path):
        """将 src_root 下所有文件（递归）平铺复制到 dest_dir，不保留中间目录层级。"""
        dest_dir.mkdir(parents=True, exist_ok=True)
        for item in src_root.rglob("*"):
            if item.is_file():
                shutil.copy2(item, dest_dir / item.name)

    # results/{model_config}/* → eval_dir/results/{suite}/*
    src_results = work_dir / "results"
    if src_results.exists():
        _copy_files_flat(src_results, eval_dir / "results" / suite)
        shutil.rmtree(src_results)

    # summary/* → eval_dir/summary/{suite}/*
    src_summary = work_dir / "summary"
    if src_summary.exists():
        _copy_files_flat(src_summary, eval_dir / "summary" / suite)
        shutil.rmtree(src_summary)

    # logs/eval/{model_config}/* → eval_dir/logs/{suite}/*
    eval_log_src = work_dir / "logs" / "eval"
    if eval_log_src.exists():
        _copy_files_flat(eval_log_src, eval_dir / "logs" / suite)
        shutil.rmtree(eval_log_src)
        # logs/ 目录若已空则清理
        logs_dir = work_dir / "logs"
        if logs_dir.exists() and not any(logs_dir.iterdir()):
            logs_dir.rmdir()


# ── 规则型任务并行执行 ────────────────────────────────────────────────
def _run_rule_tasks_parallel(
    rule_suites: list,
    meta: dict,
    model_config: str,
    infer_task_dir: Path,
    eval_dir: Path,
    max_workers: int,
    task_timeout: int,
) -> list:
    """使用线程池并行执行规则型评测任务。"""
    print(f"\n📌 规则型评测：{len(rule_suites)} 个任务，并发={max_workers}")
    print("-" * 50)

    future_to_suite = {}
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for suite in rule_suites:
            task_info = meta["tasks"][suite]
            timestamp = task_info["timestamp"]
            future = executor.submit(
                run_eval_for_task,
                suite=suite,
                timestamp=timestamp,
                task_info=task_info,
                eval_type="rule",
                model_config=model_config,
                infer_task_dir=infer_task_dir,
                eval_dir=eval_dir,
                task_timeout=task_timeout,
            )
            future_to_suite[future] = suite

        # 按完成顺序收集结果，但最终按原始顺序返回
        results_map = {}
        for future in as_completed(future_to_suite):
            suite = future_to_suite[future]
            try:
                result = future.result()
                icon = "✅" if result["status"] == "success" else "❌"
                acc = f"{result['accuracy']:.2f}%" if result["accuracy"] is not None else "N/A"
                print(f"   {icon} {suite:30s} 耗时: {result['duration_sec']}s  准确率: {acc}")
                results_map[suite] = result
            except Exception as e:
                print(f"   ❌ {suite} 异常: {e}")
                task_info = meta["tasks"][suite]
                results_map[suite] = {
                    "task": task_info["task_name"],
                    "suite": suite,
                    "type": task_info["type"],
                    "eval_type": "rule",
                    "status": "error",
                    "accuracy": None,
                    "num_samples": task_info.get("num_samples"),
                    "duration_sec": 0,
                    "returncode": -1,
                }

    # 按原始顺序返回
    return [results_map[s] for s in rule_suites]


# ── 生成评测报告 ─────────────────────────────────────────────────────
def generate_eval_report(
    results: list,
    infer_task: str,
    eval_version: str,
    model_name: str,
    eval_dir: Path,
):
    """生成 report.md 和 report.json。"""
    eval_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    accuracies = [r["accuracy"] for r in results if r["accuracy"] is not None]
    avg = sum(accuracies) / len(accuracies) if accuracies else 0.0

    # 分类汇总
    summary_stats = {
        "custom": {"count": 0, "total_duration_sec": 0.0, "accuracies": []},
        "generic": {"count": 0, "total_duration_sec": 0.0, "accuracies": []},
    }
    for r in results:
        t = r["type"]
        summary_stats[t]["count"] += 1
        summary_stats[t]["total_duration_sec"] += r["duration_sec"]
        if r["accuracy"] is not None:
            summary_stats[t]["accuracies"].append(r["accuracy"])

    for t in ["custom", "generic"]:
        accs = summary_stats[t].pop("accuracies")
        summary_stats[t]["avg_accuracy"] = (
            round(sum(accs) / len(accs), 2) if accs else 0.0
        )
        summary_stats[t]["total_duration_sec"] = round(
            summary_stats[t]["total_duration_sec"], 1
        )

    # Markdown 报告
    lines = [
        "# 评测报告",
        "",
        f"- **Infer Task**: `{infer_task}`",
        f"- **Eval Version**: `{eval_version}`",
        f"- **模型**: `{model_name}`",
        f"- **时间**: {now}",
        f"- **综合准确率**: {avg:.2f}%",
        "",
        "## 统计摘要",
        "",
        "| 任务类型 | 任务数量 | 总耗时 (秒) | 平均准确率 |",
        "|----------|----------|-------------|------------|",
        f"| 自定义 (Custom) | {summary_stats['custom']['count']} | {summary_stats['custom']['total_duration_sec']} | {summary_stats['custom']['avg_accuracy']}% |",
        f"| 通用 (Generic)  | {summary_stats['generic']['count']} | {summary_stats['generic']['total_duration_sec']} | {summary_stats['generic']['avg_accuracy']}% |",
        "",
        "## 各任务明细",
        "",
        "| 任务 | 类型 | 评估方式 | 状态 | 耗时(秒) | 数据量 | 准确率 |",
        "|------|------|----------|------|----------|--------|--------|",
    ]
    for r in results:
        status_icon = "✅" if r["status"] == "success" else "❌"
        acc_str = f"{r['accuracy']:.2f}%" if r["accuracy"] is not None else "-"
        samples_str = str(r["num_samples"]) if r["num_samples"] is not None else "-"
        lines.append(
            f"| {r['task']} | {r['type']} | {r['eval_type']} | {status_icon} {r['status']} | {r['duration_sec']} | {samples_str} | {acc_str} |"
        )

    md_path = eval_dir / "report.md"
    md_path.write_text("\n".join(lines), encoding="utf-8")

    # JSON 报告
    json_data = {
        "infer_task": infer_task,
        "eval_version": eval_version,
        "model": model_name,
        "timestamp": now,
        "avg_accuracy": round(avg, 4),
        "summary": summary_stats,
        "tasks": results,
    }
    json_path = eval_dir / "report.json"
    json_path.write_text(
        json.dumps(json_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    print(f"\n📄 评测报告已生成:")
    print(f"   Markdown : {md_path}")
    print(f"   JSON     : {json_path}")


# ── 主流程 ──────────────────────────────────────────────────────────
def main():
    args = parse_args()
    output_dir = Path(args.output_dir).resolve()
    infer_task_dir = output_dir / args.infer_task

    # 1. 读取 infer_meta.json
    meta_path = infer_task_dir / "infer_meta.json"
    if not meta_path.exists():
        print(f"❌ 找不到推理元数据: {meta_path}")
        print(f"   请先执行 eval_entry.py --task-id {args.infer_task}")
        sys.exit(1)

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    model_config = meta["model_config"]
    model_name = meta["model_name"]

    # 2. 确定评测版本
    eval_version = args.eval_version or f"eval_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
    eval_dir = infer_task_dir / eval_version
    if eval_dir.exists():
        print(f"❌ 评测版本目录已存在: {eval_dir}")
        print(f"   请指定新的 --eval-version 或删除已有目录")
        sys.exit(1)

    # 3. 确定待评测任务列表并分组
    if args.eval_tasks:
        task_suites = []
        for suite in args.eval_tasks:
            if suite not in meta["tasks"]:
                print(f"⚠️  任务 {suite} 不在 infer_meta 中，跳过")
            else:
                task_suites.append(suite)
    else:
        task_suites = list(meta["tasks"].keys())

    if not task_suites:
        print("❌ 没有可评测的任务")
        sys.exit(1)

    rule_suites, llm_suites = split_tasks_by_eval_type(task_suites)

    print("=" * 60)
    print(f"📋 infer_task              : {args.infer_task}")
    print(f"📋 eval_version            : {eval_version}")
    print(f"📋 model                   : {model_name} ({model_config})")
    print(f"📋 score_worker_concurrency: {args.score_worker_concurrency}")
    print(f"📋 规则型任务 ({len(rule_suites)})")
    for s in rule_suites:
        print(f"   - {s}")
    print(f"📋 LLM 打分任务 ({len(llm_suites)})")
    for s in llm_suites:
        print(f"   - {s}")
    print("=" * 60)

    results = []

    # 4a. 规则型任务：并行执行
    if rule_suites:
        rule_results = _run_rule_tasks_parallel(
            rule_suites=rule_suites,
            meta=meta,
            model_config=model_config,
            infer_task_dir=infer_task_dir,
            eval_dir=eval_dir,
            max_workers=args.score_worker_concurrency,
            task_timeout=args.task_timeout,
        )
        results.extend(rule_results)

    # 4b. LLM 打分任务：串行执行（打分模型 API 并发由 SCORE_LLM_CONCURRENCY 控制）
    if llm_suites and args.skip_llm:
        print(f"\n⏭️  跳过 LLM 打分评测（--skip-llm）：共 {len(llm_suites)} 个任务")
        for s in llm_suites:
            print(f"   - {s}")
    elif llm_suites:
        print(f"\n📌 LLM 打分评测：{len(llm_suites)} 个任务，串行执行")
        print("-" * 50)
        for i, suite in enumerate(llm_suites, 1):
            task_info = meta["tasks"][suite]
            timestamp = task_info["timestamp"]

            print(f"\n[{i}/{len(llm_suites)}] 🔍 评测 [llm]: {suite} (reuse={timestamp})")

            result = run_eval_for_task(
                suite=suite,
                timestamp=timestamp,
                task_info=task_info,
                eval_type="llm",
                model_config=model_config,
                infer_task_dir=infer_task_dir,
                eval_dir=eval_dir,
                task_timeout=args.task_timeout,
            )
            results.append(result)

    # 5. 生成报告
    generate_eval_report(
        results=results,
        infer_task=args.infer_task,
        eval_version=eval_version,
        model_name=model_name,
        eval_dir=eval_dir,
    )

    # 6. 打印摘要
    print("\n" + "=" * 60)
    print("📊 评测完成摘要")
    print("=" * 60)
    for r in results:
        icon = "✅" if r["status"] == "success" else "❌"
        acc = f"{r['accuracy']:.2f}%" if r["accuracy"] is not None else "N/A"
        print(
            f"  {icon} [{r['eval_type'][:3]}] {r['task']:20s} 耗时: {r['duration_sec']}s  准确率: {acc}"
        )

    accuracies = [r["accuracy"] for r in results if r["accuracy"] is not None]
    if accuracies:
        print(f"\n  🏆 综合平均: {sum(accuracies) / len(accuracies):.2f}%")
    print(f"\n  📁 结果目录: {eval_dir}")
    print("=" * 60)

    failed = [r for r in results if r["status"] != "success"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
