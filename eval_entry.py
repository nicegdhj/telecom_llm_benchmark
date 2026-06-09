#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
eval_entry.py - ais_bench 推理入口（仅推理，不做评测）

推理完成后生成 infer_meta.json，供 eval_judge.py 读取并执行评测。

用法:
    python eval_entry.py \
        --task-id round_3_v2 \
        --tasks 34 36 \
        --generic-datasets mmlu_redux_gen_5_shot_str ceval_gen_0_shot_str \
        --output-dir /results \
        --model qwen-plus \
        --concurrency 10

Docker 用法:
    docker run --rm \
        --env-file .env \
        -v /host/data:/app/data/custom_task \
        -v /host/results:/app/outputs \
        benchmark-eval:latest \
        python eval_entry.py --task-id round_1 --tasks 34 36
"""

import argparse
import gc
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

# ── 项目根目录 ──────────────────────────────────────────────────────
ROOT = Path(__file__).parent.resolve()
load_dotenv(ROOT / ".env", override=False)


# ── 参数解析 ────────────────────────────────────────────────────────
def parse_args():
    parser = argparse.ArgumentParser(
        description="ais_bench 推理入口（仅推理，不做评测）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--task-id",
        required=True,
        help="本次评测唯一标识，用于输出目录和报告命名（如 round_3_v2）",
    )
    parser.add_argument(
        "--tasks",
        nargs="*",
        default=[],
        help="要评测的自定义任务编号列表，如 34 36（对应 task_34_suite、task_36_suite）",
    )
    parser.add_argument(
        "--generic-datasets",
        nargs="*",
        default=[],
        help="要评测的通用数据集列表，如 mmlu_redux_gen_5_shot_str telequad_gen_0_shot",
    )
    parser.add_argument(
        "--data-dir",
        default=str(ROOT / "data" / "custom_task"),
        help="测试数据目录，需包含 task_XX.jsonl 文件（默认 data/custom_task）",
    )
    parser.add_argument(
        "--output-dir",
        default=str(ROOT / "outputs"),
        help="评测结果输出根目录（默认 outputs/）",
    )
    parser.add_argument(
        "--model",
        required=True,
        help="推理模型名称，用于报告标识",
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        required=True,
        help="推理并发请求数",
    )
    parser.add_argument(
        "--model-config",
        default="maas",
        choices=[
            "common_gateway",
            "local_qwen",
            "maas_gateway",
        ],
        help="指定模型配置文件：maas=私域 MaaSAPI 等（默认 maas）",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        default=False,
        help="开启调试模式：ais_bench 串行执行任务，日志实时打印到终端（默认关闭，生产环境使用并发模式）",
    )
    parser.add_argument(
        "--num-prompts",
        type=int,
        default=None,
        help="每个任务最多评测多少条数据（默认 None 表示全量）。透传给 ais_bench --num-prompts。",
    )
    args = parser.parse_args()

    if not args.tasks and not args.generic_datasets:
        parser.error("Must specify at least one of --tasks or --generic-datasets")

    return args


# ── 清理泄漏的共享内存 ────────────────────────────────────────────────
def _cleanup_leaked_shm():
    """清理 /dev/shm 中残留的 Python 共享内存段，防止 OOM。

    Python multiprocessing.shared_memory 创建的共享内存以 /psm_ 或 /wnsm_ 为前缀，
    存放在 /dev/shm/ 下。当进程被 SIGKILL 后这些文件不会自动删除。
    """
    shm_dir = Path("/dev/shm")
    if not shm_dir.exists():
        return
    cleaned = 0
    for f in shm_dir.iterdir():
        # Python SharedMemory 默认命名格式
        if f.name.startswith(("psm_", "wnsm_")):
            try:
                f.unlink()
                cleaned += 1
            except OSError:
                pass
    if cleaned:
        print(f"   🧹 已清理 {cleaned} 个残留共享内存段")


# ── 数据文件校验 ────────────────────────────────────────────────────
def validate_data_files(task_nums: list, data_dir: Path):
    if not task_nums:
        return
    missing = []
    for num in task_nums:
        p = data_dir / f"task_{num}.jsonl"
        # 也支持目录结构：data/task_N/ 目录（内含多个 jsonl 文件）
        p_dir = data_dir.parent / f"task_{num}"
        if not p.exists() and not p_dir.is_dir():
            missing.append(str(p))
    if missing:
        print("❌ 以下自定义任务数据文件不存在，请检查 --data-dir 路径：")
        for f in missing:
            print(f"   {f}")
        sys.exit(1)
    print(f"✅ 自定义任务数据文件校验通过（{len(task_nums)} 个任务）")


# ── 设置数据目录软链（当 data-dir 不是默认路径时） ─────────────────
def setup_data_symlink(data_dir: Path):
    default_dir = ROOT / "data" / "custom_task"
    if data_dir.resolve() == default_dir.resolve():
        return  # 已是默认路径，无需处理

    print(f"🔗 将自定义数据目录软链至: {data_dir}")
    default_dir.parent.mkdir(parents=True, exist_ok=True)
    if default_dir.is_symlink() or default_dir.exists():
        if default_dir.is_symlink():
            default_dir.unlink()
        else:
            shutil.rmtree(default_dir)
    default_dir.symlink_to(data_dir.resolve())


# ── 执行评测 ────────────────────────────────────────────────────────
def run_evaluation(
    task_nums: list,
    generic_datasets: list,
    output_dir: Path,
    task_id: str,
    model_config: str = "maas",
    concurrency: int = 1,
    debug: bool = False,
    num_prompts: int = None,
) -> list:

    # 构造任务队列，格式 (任务名, suite名称, 任务类型)
    queue = []
    for num in task_nums:
        queue.append((f"task_{num}", f"task_{num}_suite", "custom"))
    for dset in generic_datasets:
        queue.append((dset, dset, "generic"))

    ais_bench_output = ROOT / "outputs" / "default"
    # 每次评测前清理旧的 default 目录，避免历史结果占用磁盘
    if ais_bench_output.exists():
        shutil.rmtree(ais_bench_output)
    ais_bench_output.mkdir(parents=True, exist_ok=True)
    results = []

    for i, (task_name, suite, task_type) in enumerate(queue, 1):
        if debug:
            print(
                f"\n[{i}/{len(queue)}] 🐛 执行任务 [{task_type}] (debug串行): {suite}"
            )
            # --debug 模式：ais_bench 串行执行，日志直接打印到终端，便于排查问题
            cmd = [
                "ais_bench",
                "--mode", "infer",
                "--models",
                model_config,
                "--datasets",
                suite,
                "--debug",
            ]
        else:
            print(
                f"\n[{i}/{len(queue)}] 🚀 执行任务 [{task_type}] (并发={concurrency}): {suite}"
            )
            # 生产模式：去掉 --debug，用 --max-num-workers 开启真正并发
            cmd = [
                "ais_bench",
                "--mode", "infer",
                "--models",
                model_config,
                "--datasets",
                suite,
                "--max-num-workers",
                str(concurrency),
            ]
        # 若指定了 --num-prompts，追加给 ais_bench（debug 和并发模式均生效）
        if num_prompts is not None:
            cmd += ["--num-prompts", str(num_prompts)]

        start_time = time.time()
        proc = subprocess.run(
            cmd,
            cwd=str(ROOT),
            text=True,
            capture_output=False,  # 实时输出到终端
        )
        duration = time.time() - start_time

        # infer 模式不产出 summary/results，只需找到时间戳目录和样本数
        ais_bench_dir, num_samples = _find_infer_output(
            ais_bench_output, suite_name_pattern=suite, run_start_time=start_time
        )
        # ais_bench CLI 在 warmup 失败等场景下仍可能 exit 0（异常被内部捕获），
        # 因此真正的成功信号是：①子进程退出码=0 ②产出目录与样本数都存在。
        # 任一缺失即视为 failed，避免下游 eval 拿到 timestamp=None 崩溃。
        infer_ok = (
            proc.returncode == 0
            and ais_bench_dir is not None
            and num_samples is not None
            and num_samples > 0
        )
        results.append(
            {
                "task_name": task_name,
                "type": task_type,
                "suite": suite,
                "status": "success" if infer_ok else "failed",
                "num_samples": num_samples,
                "duration_sec": round(duration, 1),
                "returncode": proc.returncode,
                "timestamp": ais_bench_dir,
            }
        )
        if not infer_ok:
            print(
                f"   ❌ 推理失败: returncode={proc.returncode}, "
                f"timestamp={ais_bench_dir}, num_samples={num_samples}"
            )

        # ── 逐任务清理：清理残留共享内存 + 搬运产出 + 强制 GC ──
        _cleanup_leaked_shm()
        gc.collect()

        if ais_bench_dir:
            src_dir = ais_bench_output / ais_bench_dir
            if src_dir.exists():
                staging_dir = output_dir / task_id / "details" / ais_bench_dir
                staging_dir.parent.mkdir(parents=True, exist_ok=True)
                shutil.copytree(src_dir, staging_dir)
                shutil.rmtree(src_dir)
                print(f"   📦 已转存并清理: {ais_bench_dir}")

    return results


def _find_infer_output(
    ais_bench_output: Path, suite_name_pattern: str, run_start_time: float = None
) -> tuple:
    """查找本次推理产出的时间戳目录和样本数。

    Args:
        ais_bench_output: ais_bench 输出根目录（outputs/default/）
        suite_name_pattern: 当前任务的 suite 名称
        run_start_time: 调用 ais_bench 前的 time.time()，用于时间过滤

    Returns:
        (dir_name: str | None, num_samples: int | None)
    """
    try:
        candidates = []
        for d in ais_bench_output.iterdir():
            if not d.is_dir():
                continue
            pred_dir = d / "predictions"
            if not pred_dir.exists():
                continue
            # 时间过滤
            if run_start_time is not None and d.stat().st_mtime <= (run_start_time - 300):
                continue
            # config 匹配
            for cfg in d.glob("configs/*.py"):
                try:
                    cfg_text = cfg.read_text(encoding="utf-8")
                    if f"'{suite_name_pattern}'" in cfg_text or f'"{suite_name_pattern}"' in cfg_text:
                        candidates.append(d)
                        break
                except Exception:
                    pass

        if not candidates:
            return None, None

        # 取最新的
        target = sorted(candidates, key=lambda p: p.stat().st_mtime, reverse=True)[0]
        dir_name = target.name

        # 统计样本数
        num_samples = None
        jsonl_files = list((target / "predictions").glob("**/*.jsonl"))
        if jsonl_files:
            try:
                num_samples = sum(
                    sum(1 for _ in open(f, "r", encoding="utf-8"))
                    for f in jsonl_files
                )
            except Exception:
                pass

        return dir_name, num_samples
    except Exception:
        return None, None


# ── 生成推理元数据 ────────────────────────────────────────────────────
def generate_infer_meta(results: list, task_id: str, model_config: str, model_name: str, output_dir: Path):
    """生成 infer_meta.json，记录每个任务的推理时间戳映射。"""
    meta = {
        "task_id": task_id,
        "model_config": model_config,
        "model_name": model_name,
        "infer_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tasks": {}
    }
    for r in results:
        meta["tasks"][r["suite"]] = {
            "timestamp": r["timestamp"],
            "task_name": r["task_name"],
            "type": r["type"],
            "num_samples": r["num_samples"],
            "duration_sec": r["duration_sec"],
            "status": r["status"],
        }

    meta_path = output_dir / task_id / "infer_meta.json"
    meta_path.parent.mkdir(parents=True, exist_ok=True)
    meta_path.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n📄 推理元数据已生成: {meta_path}")

    # 兜底：搬运 outputs/default 中残余目录
    ais_out = ROOT / "outputs" / "default"
    dest_details = output_dir / task_id / "details"
    dest_details.mkdir(parents=True, exist_ok=True)
    if ais_out.exists():
        for sub in ais_out.iterdir():
            dest_sub = dest_details / sub.name
            if sub.is_dir() and not dest_sub.exists():
                shutil.copytree(sub, dest_sub)
        shutil.rmtree(ais_out)


# ── 主流程 ──────────────────────────────────────────────────────────
def main():
    args = parse_args()

    # 注入到环境变量（子进程 ais_bench 会继承）
    # local_qwen 的 batch_size 读取 LOCAL_CONCURRENCY
    os.environ["LOCAL_CONCURRENCY"] = str(args.concurrency)

    data_dir = Path(args.data_dir).resolve()
    output_dir = Path(args.output_dir).resolve()

    print("=" * 60)
    print(f"📋 task_id          : {args.task_id}")
    print(f"📋 custom tasks     : {args.tasks}")
    print(f"📋 generic datasets : {args.generic_datasets}")
    print(f"📋 model            : {args.model} (并发 {args.concurrency})")
    print(f"📋 data_dir         : {data_dir}")
    print(f"📋 output_dir       : {output_dir / args.task_id}")
    print("=" * 60)

    validate_data_files(args.tasks, data_dir)
    setup_data_symlink(data_dir)

    results = run_evaluation(
        task_nums=args.tasks,
        generic_datasets=args.generic_datasets,
        output_dir=output_dir,
        task_id=args.task_id,
        model_config=args.model_config,
        concurrency=args.concurrency,
        debug=args.debug,
        num_prompts=args.num_prompts,
    )
    generate_infer_meta(results, args.task_id, args.model_config, args.model, output_dir)

    # 打印摘要
    print("\n" + "=" * 60)
    print("📊 推理完成摘要")
    print("=" * 60)
    for r in results:
        icon = "✅" if r["status"] == "success" else "❌"
        samples = r["num_samples"] if r["num_samples"] else "N/A"
        print(
            f"  {icon} [{r['type'][:3]}] {r['task_name']:15s} 耗时: {r['duration_sec']}s  样本数: {samples}"
        )
    print(f"\n  📁 结果目录: {output_dir / args.task_id}")
    print("=" * 60)

    # 外部调用时返回非 0 表示有任务失败
    failed = [r for r in results if r["status"] != "success"]
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
