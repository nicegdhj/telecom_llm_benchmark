#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
aggregate_default_reports.py - 汇总 ais_bench 原生输出（outputs/default/<timestamp>）的评测结果

读取 outputs/default 下各时间戳目录中 results/<model>/<task>.json 的评分，
按 aggregate_eval_reports.py 相同的结构产出汇总 Excel：
    - 总体对比 sheet（Task × 模型，含准确率 / token_full_mean / token_COT_mean 分组列）
      + 任务映射关系附录
    - 每个模型一个 sheet（Custom/Generic 概览 + 任务明细表）
    - 指标明细 sheet（每个任务的全部子指标）

用法（与 aggregate_eval_reports.py 接口对齐）：
    python aggregate_default_reports.py \\
        --default-dir outputs/default \\
        --output-dir ./outputs \\
        --tokenizer-path ./scripts/token_count/tokenizers/qwen3 \\
        --workers 8

不传 --tokenizer-path（或路径不存在）时 token 列留空（与 aggregate_eval_reports.py 行为一致）。
"""

import argparse
import concurrent.futures
import glob
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# 复用原脚本的 CoT 提取逻辑，保证 token 统计口径一致
from aggregate_eval_reports import extract_cot_text


# ── 任务名映射（复用 aggregate_eval_reports.py 逻辑）────────────────────────────

def load_task_mapping(output_base_dir: str):
    """读取 评测任务文件名对应.xlsx：任务文件名 -> (中文数据集名, 通用/垂类)。"""
    name_map: Dict[str, str] = {}
    category_map: Dict[str, str] = {}
    df_task_mapping = None
    f = os.path.join(output_base_dir, "评测任务文件名对应.xlsx")
    if os.path.exists(f):
        df_task_mapping = pd.read_excel(f)
        cols = list(df_task_mapping.columns)
        for _, row in df_task_mapping.iterrows():
            k = str(row.iloc[0]).strip()
            v = str(row.iloc[1]).strip() if len(cols) >= 2 else k
            if k and k != "nan" and v != "nan":
                name_map[k] = v
            if len(cols) >= 3:
                cat = str(row.iloc[2]).strip()
                if k and cat and cat != "nan":
                    category_map[k] = cat
    return name_map, category_map, df_task_mapping


def get_mapped_suite(raw_suite: str, name_map: dict) -> str:
    """查映射表，找不到时尝试去掉常见后缀再查，再找不到返回原名。"""
    if raw_suite in name_map:
        return name_map[raw_suite]
    for suffix in ("_suite",):
        stripped = raw_suite.removesuffix(suffix)
        if stripped in name_map:
            return name_map[stripped]
    return raw_suite


def get_category(raw_suite: str, category_map: dict) -> str:
    """返回 通用/垂类，找不到默认垂类（自定义 task 多为垂类）。"""
    if raw_suite in category_map:
        return category_map[raw_suite]
    return "垂类"


# ── 解析单个 results json ──────────────────────────────────────────────────────

PRIMARY_KEY = "accuracy"


def extract_metrics(result_json: dict) -> Dict[str, float]:
    """提取数值型指标（剔除 type 等非数值字段）。"""
    out = {}
    for k, v in result_json.items():
        if k == "type":
            continue
        if isinstance(v, (int, float)):
            out[k] = v
    return out


def pick_primary(metrics: Dict[str, float]) -> Optional[float]:
    """选主指标：优先 accuracy，其次 *llm_judge_percentage（多个取均值），否则 None。"""
    if PRIMARY_KEY in metrics:
        return metrics[PRIMARY_KEY]
    judge_vals = [v for k, v in metrics.items() if k.endswith("llm_judge_percentage")]
    if judge_vals:
        return sum(judge_vals) / len(judge_vals)
    return None


def count_samples(details_path: Path) -> int:
    if not details_path.exists():
        return 0
    n = 0
    with open(details_path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                n += 1
    return n


# ── Token 统计（多进程 worker，复用原脚本口径）──────────────────────────────────

_WORKER_TOKENIZER = None


def _worker_init(tokenizer_path: Optional[str]):
    global _WORKER_TOKENIZER
    if tokenizer_path and Path(tokenizer_path).exists():
        from transformers import AutoTokenizer
        _WORKER_TOKENIZER = AutoTokenizer.from_pretrained(
            tokenizer_path, trust_remote_code=True, local_files_only=True
        )
    else:
        _WORKER_TOKENIZER = None


def _get_prediction_text(obj: dict) -> Optional[str]:
    """从 details 行中取出预测文本（prediction 为 dict 时取其 prediction 字段）。"""
    pred = obj.get("prediction")
    if isinstance(pred, dict):
        val = pred.get("prediction")
        return val if isinstance(val, str) else None
    if isinstance(pred, str):
        try:
            parsed = json.loads(pred)
            if isinstance(parsed, dict):
                val = parsed.get("prediction")
                return val if isinstance(val, str) else None
        except json.JSONDecodeError:
            pass
        return pred
    return None


def _count_task_tokens(args: Tuple[str, str, str]) -> Dict[str, Any]:
    """统计单个任务的 full / cot token，返回聚合 mean/max/samples。"""
    model, raw_task, details_path = args
    result = {"model": model, "raw_task": raw_task,
              "full_mean": None, "cot_mean": None,
              "full_max": 0, "cot_max": 0, "samples": 0}
    if _WORKER_TOKENIZER is None or not Path(details_path).exists():
        return result

    full_texts, cot_texts = [], []
    with open(details_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = _get_prediction_text(obj)
            if not text:
                continue
            full_texts.append(text)
            cot = extract_cot_text(text)
            cot_texts.append(cot if cot else "")

    if not full_texts:
        return result

    enc = _WORKER_TOKENIZER.backend_tokenizer.encode_batch(full_texts)
    full_lens = [len(e.ids) for e in enc]
    enc_cot = _WORKER_TOKENIZER.backend_tokenizer.encode_batch(cot_texts)
    cot_lens = [len(e.ids) if t else 0 for e, t in zip(enc_cot, cot_texts)]

    result["samples"] = len(full_lens)
    result["full_mean"] = round(sum(full_lens) / len(full_lens), 2)
    result["full_max"] = max(full_lens)
    result["cot_mean"] = round(sum(cot_lens) / len(cot_lens), 2)
    result["cot_max"] = max(cot_lens)
    return result


def compute_token_stats(models: dict, default_dir: str,
                        tokenizer_path: Optional[str], workers: int) -> Dict[Tuple[str, str], dict]:
    """返回 {(model, raw_task): token_stats}。无 tokenizer 时返回空。"""
    if not (tokenizer_path and Path(tokenizer_path).exists()):
        if tokenizer_path:
            print(f"⚠️ tokenizer 路径不存在，跳过 token 统计: {tokenizer_path}")
        return {}

    tasks: List[Tuple[str, str, str]] = []
    for model, task_recs in models.items():
        for raw_task, rec in task_recs.items():
            details = os.path.join(
                default_dir, rec["timestamp"], "results", model, f"{raw_task}_details.jsonl"
            )
            tasks.append((model, raw_task, details))

    print(f"📊 计算 token 统计：{len(tasks)} 个任务（workers={workers}）...")
    stats: Dict[Tuple[str, str], dict] = {}
    if workers > 1:
        with concurrent.futures.ProcessPoolExecutor(
            max_workers=workers, initializer=_worker_init, initargs=(tokenizer_path,)
        ) as ex:
            for r in ex.map(_count_task_tokens, tasks):
                stats[(r["model"], r["raw_task"])] = r
    else:
        _worker_init(tokenizer_path)
        for t in tasks:
            r = _count_task_tokens(t)
            stats[(r["model"], r["raw_task"])] = r
    return stats


# ── 扫描 outputs/default ───────────────────────────────────────────────────────

def scan_default(default_dir: str):
    """
    返回 {model: {raw_task: {"metrics": {...}, "primary": float|None,
                             "num_samples": int, "timestamp": str}}}
    多个时间戳出现同一 (model, task) 时，保留时间戳较新的那个。
    """
    models: Dict[str, Dict[str, Any]] = {}
    for ts_dir in sorted(os.scandir(default_dir), key=lambda e: e.name):
        if not ts_dir.is_dir():
            continue
        timestamp = ts_dir.name
        results_root = Path(ts_dir.path) / "results"
        if not results_root.exists():
            continue
        for model_dir in os.scandir(results_root):
            if not model_dir.is_dir():
                continue
            model = model_dir.name
            for jf in glob.glob(os.path.join(model_dir.path, "*.json")):
                raw_task = os.path.splitext(os.path.basename(jf))[0]
                try:
                    data = json.loads(Path(jf).read_text(encoding="utf-8"))
                except Exception as e:
                    print(f"❌ 读取 {jf} 失败: {e}")
                    continue
                metrics = extract_metrics(data)
                details = Path(jf).with_name(f"{raw_task}_details.jsonl")
                record = {
                    "metrics": metrics,
                    "primary": pick_primary(metrics),
                    "num_samples": count_samples(details),
                    "timestamp": timestamp,
                }
                slot = models.setdefault(model, {})
                prev = slot.get(raw_task)
                if prev is None or timestamp >= prev["timestamp"]:
                    slot[raw_task] = record
    return models


# ── 生成 Excel ─────────────────────────────────────────────────────────────────

def build_report(default_dir: str, output_base_dir: str,
                 tokenizer_path: Optional[str] = None, workers: int = 1):
    name_map, category_map, df_task_mapping = load_task_mapping(output_base_dir)
    models = scan_default(default_dir)
    if not models:
        print("❌ 未在 outputs/default 下找到任何 results，已退出")
        return

    model_names = sorted(models.keys())
    # 全部任务（原始名）
    all_tasks = sorted({t for m in models.values() for t in m})
    print(f"✅ 模型 {len(model_names)} 个，任务 {len(all_tasks)} 个")

    # token 统计：{(model, raw_task): {full_mean, cot_mean, full_max, cot_max, samples}}
    token_stats = compute_token_stats(models, default_dir, tokenizer_path, workers)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target_dir = os.path.join(output_base_dir, f"default_aggregated_reports_{timestamp}")
    os.makedirs(target_dir, exist_ok=True)
    summary_excel = os.path.join(target_dir, "default_总体汇总.xlsx")

    # ── 总体对比（MultiIndex 列）──────────────────────────────────────────────
    task_labels = [get_mapped_suite(t, name_map) for t in all_tasks]
    df_result = pd.DataFrame(index=pd.Index(task_labels, name="Task"))

    for grp in ("准确率", "token_full_mean", "token_COT_mean"):
        for model in model_names:
            vals = []
            for t in all_tasks:
                rec = models[model].get(t)
                if grp == "准确率":
                    vals.append(round(rec["primary"], 2) if rec and rec["primary"] is not None else None)
                elif grp == "token_full_mean":
                    ts = token_stats.get((model, t))
                    vals.append(ts["full_mean"] if ts else None)
                else:  # token_COT_mean
                    ts = token_stats.get((model, t))
                    vals.append(ts["cot_mean"] if ts else None)
            df_result[(grp, model)] = vals
        if grp != "token_COT_mean":
            df_result[("", f"_sep_{grp}")] = None  # 空分隔列

    # 按 准确率 / 空 / token_full / 空 / token_COT 排列列
    ordered_cols = []
    for model in model_names:
        ordered_cols.append(("准确率", model))
    ordered_cols.append(("", "_sep_准确率"))
    for model in model_names:
        ordered_cols.append(("token_full_mean", model))
    ordered_cols.append(("", "_sep_token_full_mean"))
    for model in model_names:
        ordered_cols.append(("token_COT_mean", model))
    df_result = df_result[ordered_cols]
    df_result.columns = pd.MultiIndex.from_tuples(
        [(g, "" if s.startswith("_sep_") else s) for g, s in df_result.columns]
    )

    with pd.ExcelWriter(summary_excel, engine="openpyxl") as writer:
        df_result.to_excel(writer, sheet_name="总体对比")
        ws = writer.sheets["总体对比"]

        # 任务映射关系附录
        current_row = len(df_result) + 4
        if df_task_mapping is not None:
            ws.cell(row=current_row, column=1).value = "【附录 1】任务映射关系"
            df_task_mapping.to_excel(
                writer, sheet_name="总体对比", startrow=current_row, index=False
            )

        # 指标明细 sheet（所有任务的全部子指标）
        detail_rows: List[Dict[str, Any]] = []
        for model in model_names:
            for t in all_tasks:
                rec = models[model].get(t)
                if not rec:
                    continue
                for metric, val in rec["metrics"].items():
                    detail_rows.append({
                        "model": model,
                        "suite": t,
                        "task": get_mapped_suite(t, name_map),
                        "metric": metric,
                        "value": round(val, 2),
                        "num_samples": rec["num_samples"],
                        "timestamp": rec["timestamp"],
                    })
        pd.DataFrame(detail_rows).to_excel(writer, sheet_name="指标明细", index=False)

        # 每个模型一个 sheet：Custom/Generic 概览 + 任务明细表
        for model in model_names:
            tasks_list = []
            custom_cnt = generic_cnt = 0
            custom_acc, generic_acc = [], []
            for t in all_tasks:
                rec = models[model].get(t)
                if not rec:
                    continue
                cat = get_category(t, category_map)
                acc = rec["primary"]
                if cat == "通用":
                    generic_cnt += 1
                    if acc is not None:
                        generic_acc.append(acc)
                else:
                    custom_cnt += 1
                    if acc is not None:
                        custom_acc.append(acc)
                tasks_list.append({
                    "suite": t,
                    "task": get_mapped_suite(t, name_map),
                    "category": cat,
                    "type": rec["metrics"].get("type", "GEN") if isinstance(rec["metrics"], dict) else "GEN",
                    "status": "done",
                    "accuracy": round(acc, 2) if acc is not None else None,
                    "num_samples": rec["num_samples"],
                    "timestamp": rec["timestamp"],
                })

            df_sum = pd.DataFrame({
                "Type": ["Custom", "Generic"],
                "Count": [custom_cnt, generic_cnt],
                "Avg Accuracy": [
                    round(sum(custom_acc) / len(custom_acc), 2) if custom_acc else 0,
                    round(sum(generic_acc) / len(generic_acc), 2) if generic_acc else 0,
                ],
            })
            df_tasks = pd.DataFrame(tasks_list)

            sheet_name = str(model)[:31]
            df_sum.to_excel(writer, sheet_name=sheet_name, index=False, startrow=0)
            df_tasks.to_excel(
                writer, sheet_name=sheet_name, index=False, startrow=len(df_sum) + 3
            )

            # 追加 Token 统计到 sheet 底部（与 aggregate_eval_reports.py 一致）
            token_rows = []
            for t in all_tasks:
                ts = token_stats.get((model, t))
                if not ts or ts["samples"] == 0:
                    continue
                token_rows.append({
                    "task": get_mapped_suite(t, name_map),
                    "samples": ts["samples"],
                    "full_mean": ts["full_mean"],
                    "cot_mean": ts["cot_mean"],
                    "full_max": ts["full_max"],
                    "cot_max": ts["cot_max"],
                })
            if token_rows:
                ws_m = writer.sheets[sheet_name]
                start = ws_m.max_row + 2
                ws_m.cell(row=start, column=1, value="【Token 统计】")
                pd.DataFrame(token_rows).to_excel(
                    writer, sheet_name=sheet_name, index=False, startrow=start
                )

    print(f"📊 总体汇总 Excel: {summary_excel}")
    print(f"✅ 汇总完成 → {target_dir}")


def main():
    parser = argparse.ArgumentParser(
        description="汇总 ais_bench 原生输出（outputs/default）的评测结果为 Excel",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--default-dir", default="outputs/default", help="outputs/default 目录")
    parser.add_argument("--output-dir", default="outputs", help="映射表所在 & 汇总输出目录")
    parser.add_argument("--tokenizer-path", default=None,
                        help="tokenizer 路径，用于统计 prediction 的 token 数（缺省则不统计）")
    parser.add_argument("--workers", type=int, default=1, help="并发 worker 数")
    args = parser.parse_args()
    build_report(args.default_dir, args.output_dir, args.tokenizer_path, args.workers)


if __name__ == "__main__":
    main()
