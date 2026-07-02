#!/usr/bin/env python3
"""
把 SRC_ROOT/<model>/eval_init_batch/ 下 3 个补跑任务的结果合并到
DST_ROOT/<model>/eval_init/ 中，同时替换 details/<timestamp>/
和更新 infer_meta.json 对应条目。

用法:
    python merge_patch_into_formal.py                # dry-run
    python merge_patch_into_formal.py --apply        # 真正执行
"""
import argparse
import json
import shutil
import sys
from pathlib import Path

SRC_ROOT = Path("/Users/jia/windowsShare/newfmt_llm")
DST_ROOT = Path("/Users/jia/windowsShare/formal0416")
SRC_EVAL_VERSION = "eval_init_batch"
DST_EVAL_VERSION = "eval_init"
TARGET_SUITES = [
    "telequad_gen_0_shot",
    "tele_exam_gen_0_shot_str",
    "identity_gen_0_shot",
]


def parse_list(val):
    return [s for s in val.replace(",", " ").split() if s]


def log(msg, dry):
    prefix = "[DRY] " if dry else "[DO ] "
    print(prefix + msg)


def replace_dir(src: Path, dst: Path, dry: bool):
    if not src.exists():
        print(f"  ⚠️  源不存在，跳过: {src}")
        return
    if dst.exists():
        log(f"rm -rf {dst}", dry)
        if not dry:
            shutil.rmtree(dst)
    log(f"cp -r {src} → {dst}", dry)
    if not dry:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)


def process_model(model: str, dry: bool):
    print(f"\n=== 模型: {model} ===")
    src_model = SRC_ROOT / model
    dst_model = DST_ROOT / model

    src_meta_path = src_model / "infer_meta.json"
    dst_meta_path = dst_model / "infer_meta.json"

    if not src_meta_path.exists():
        print(f"  ❌ 跳过：{src_meta_path} 不存在")
        return
    if not dst_meta_path.exists():
        print(f"  ❌ 跳过：{dst_meta_path} 不存在")
        return

    src_meta = json.loads(src_meta_path.read_text(encoding="utf-8"))
    dst_meta = json.loads(dst_meta_path.read_text(encoding="utf-8"))

    for suite in TARGET_SUITES:
        if suite not in src_meta["tasks"]:
            print(f"  ⚠️  源 infer_meta 缺 {suite}，跳过")
            continue

        src_info = src_meta["tasks"][suite]
        timestamp = src_info.get("timestamp")
        task_name = src_info.get("task_name", suite)
        print(
            f"  [{suite}] task_name={task_name} timestamp={timestamp} "
            f"samples={src_info.get('num_samples')}"
        )

        # 1) 替换 details/<timestamp>/
        if timestamp:
            src_dt = src_model / "details" / timestamp
            dst_dt = dst_model / "details" / timestamp
            replace_dir(src_dt, dst_dt, dry)
        else:
            print(f"    ⚠️  {suite} 源 timestamp 为空，details 不替换")

        # 2) 替换 eval_init/<logs|results|summary>/<suite>/
        for sub in ("logs", "results", "summary"):
            src_sub = src_model / SRC_EVAL_VERSION / sub / suite
            dst_sub = dst_model / DST_EVAL_VERSION / sub / suite
            replace_dir(src_sub, dst_sub, dry)

        # 3) 更新 infer_meta.json 里对应条目
        old = dst_meta["tasks"].get(suite)
        dst_meta["tasks"][suite] = src_info
        log(f"update infer_meta.json[{suite}] : {old} → {src_info}", dry)

    # 写回 meta
    log(f"write {dst_meta_path}", dry)
    if not dry:
        dst_meta_path.write_text(
            json.dumps(dst_meta, ensure_ascii=False, indent=2), encoding="utf-8"
        )


def main():
    global SRC_ROOT, DST_ROOT, SRC_EVAL_VERSION, DST_EVAL_VERSION, TARGET_SUITES
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="真正执行（默认 dry-run）")
    ap.add_argument("--src-root", default=str(SRC_ROOT))
    ap.add_argument("--dst-root", default=str(DST_ROOT))
    ap.add_argument("--src-eval-version", default=SRC_EVAL_VERSION)
    ap.add_argument("--dst-eval-version", default=DST_EVAL_VERSION)
    ap.add_argument("--suites", default=" ".join(TARGET_SUITES),
                    help="空格或逗号分隔的 suite 名")
    args = ap.parse_args()
    dry = not args.apply

    SRC_ROOT = Path(args.src_root)
    DST_ROOT = Path(args.dst_root)
    SRC_EVAL_VERSION = args.src_eval_version
    DST_EVAL_VERSION = args.dst_eval_version
    TARGET_SUITES = parse_list(args.suites)
    print(f"📋 SRC: {SRC_ROOT}/<model>/{SRC_EVAL_VERSION}")
    print(f"📋 DST: {DST_ROOT}/<model>/{DST_EVAL_VERSION}")
    print(f"📋 Suites: {TARGET_SUITES}")

    if not SRC_ROOT.exists():
        print(f"❌ 源目录不存在: {SRC_ROOT}")
        sys.exit(1)
    if not DST_ROOT.exists():
        print(f"❌ 目标目录不存在: {DST_ROOT}")
        sys.exit(1)

    models = sorted(
        d.name for d in SRC_ROOT.iterdir()
        if d.is_dir() and (d / "infer_meta.json").exists()
    )
    print(f"🔍 将处理 {len(models)} 个模型: {models}")
    print(f"🔍 模式: {'DRY-RUN (不改动文件)' if dry else 'APPLY (真正执行)'}")

    for model in models:
        process_model(model, dry)

    print("\n✅ 完成" + (" (dry-run)" if dry else ""))


if __name__ == "__main__":
    main()
