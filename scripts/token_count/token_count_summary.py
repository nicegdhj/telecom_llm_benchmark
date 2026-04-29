# -*- coding: utf-8 -*-
"""
读取已有 token_count 列并生成统计分析结果。

目录结构假设：
./
  ├── token_count_summary.py
  ├── AIME-2025/
  │   ├── qwen3_32b_think/
  │   │   ├── result.xlsx
  │   │   └── ...
  │   └── ...
  └── ...

处理范围：
  只读取 ./任务文件夹/模型文件夹/*.xlsx
  不读取根目录下的 xlsx
  不递归读取更深层目录

功能：
  1. 读取每个 Excel 中已有的 token_count 列
  2. 生成文件级统计 file_summary
  3. 生成模型级统计 model_summary
  4. 生成任务级统计 task_summary
  5. 生成任务+模型级统计 task_model_summary
  6. 统计 p90 / p95 / p99
  7. 统计 >=4k / >=8k / >=16k token 的数量和比例
  8. token 数值字段输出为整数
  9. 比例字段输出为百分数，保留两位小数
  10. 输出到 token_count_summary.xlsx

用法：
  python token_count_summary.py

可选参数：
  python token_count_summary.py --root .
  python token_count_summary.py --output token_count_summary.xlsx
"""

import argparse
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd


IGNORED_DIRS = {
    "tokenizers",
    "__pycache__",
    ".git",
    ".vscode",
    ".idea",
}


TOKEN_THRESHOLDS = {
    "4k": 4096,
    "8k": 8192,
    "16k": 16384,
}


TOKEN_VALUE_COLS = [
    "mean_token",
    "median_token",
    "p90_token",
    "p95_token",
    "p99_token",
    "min_token",
    "max_token",
    "sum_token",
]


RATE_COLS = [
    "over_4k_rate",
    "over_8k_rate",
    "over_16k_rate",
]


def is_task_dir(path: Path) -> bool:
    """判断是否应作为任务目录处理。"""
    return path.is_dir() and path.name not in IGNORED_DIRS


def scan_target_excels(root: Path) -> List[Dict[str, Path]]:
    """
    扫描目标 Excel 文件。

    只扫描：
      ./任务文件夹/模型文件夹/*.xlsx
    """
    targets: List[Dict[str, Path]] = []

    for task_dir in sorted(root.iterdir(), key=lambda p: p.name):
        if not is_task_dir(task_dir):
            continue

        for model_dir in sorted(task_dir.iterdir(), key=lambda p: p.name):
            if not model_dir.is_dir():
                continue

            for xlsx_path in sorted(model_dir.glob("*.xlsx"), key=lambda p: p.name):
                if xlsx_path.name.startswith("~$"):
                    continue

                targets.append(
                    {
                        "task_dir": task_dir,
                        "model_dir": model_dir,
                        "xlsx_path": xlsx_path,
                    }
                )

    return targets


def summarize_excel(
    xlsx_path: Path,
    task_name: str,
    model_name: str,
) -> Dict[str, Any]:
    """
    对单个 Excel 中已有 token_count 列做统计。
    """
    record: Dict[str, Any] = {
        "task": task_name,
        "model": model_name,
        "file": str(xlsx_path),
        "file_name": xlsx_path.name,
        "processed": False,
        "rows": None,
        "valid_token_rows": None,
        "missing_token_count": None,
        "mean_token": None,
        "median_token": None,
        "p90_token": None,
        "p95_token": None,
        "p99_token": None,
        "min_token": None,
        "max_token": None,
        "sum_token": None,
        "over_4k_count": None,
        "over_8k_count": None,
        "over_16k_count": None,
        "over_4k_rate": None,
        "over_8k_rate": None,
        "over_16k_rate": None,
        "skipped_reason": None,
        "error": None,
    }

    try:
        df = pd.read_excel(xlsx_path)
        record["rows"] = len(df)

        if "token_count" not in df.columns:
            record["skipped_reason"] = "missing_token_count_column"
            return record

        token_series = pd.to_numeric(df["token_count"], errors="coerce")
        valid_token_series = token_series.dropna()

        record["valid_token_rows"] = len(valid_token_series)
        record["missing_token_count"] = int(token_series.isna().sum())

        if len(valid_token_series) == 0:
            record["skipped_reason"] = "empty_token_count_column"
            return record

        valid_count = len(valid_token_series)

        record["processed"] = True
        record["mean_token"] = float(valid_token_series.mean())
        record["median_token"] = float(valid_token_series.median())
        record["p90_token"] = float(valid_token_series.quantile(0.90))
        record["p95_token"] = float(valid_token_series.quantile(0.95))
        record["p99_token"] = float(valid_token_series.quantile(0.99))
        record["min_token"] = int(valid_token_series.min())
        record["max_token"] = int(valid_token_series.max())
        record["sum_token"] = int(valid_token_series.sum())

        for label, threshold in TOKEN_THRESHOLDS.items():
            count_col = f"over_{label}_count"
            rate_col = f"over_{label}_rate"

            over_count = int((valid_token_series >= threshold).sum())
            record[count_col] = over_count
            record[rate_col] = over_count / valid_count

        return record

    except Exception as e:
        record["skipped_reason"] = "error"
        record["error"] = repr(e)
        return record


def collect_token_details(targets: List[Dict[str, Path]]) -> pd.DataFrame:
    """
    收集所有已处理 Excel 的样本级 token_count 明细。

    这样 task/model/task+model 聚合时，可以计算严格的：
      - median
      - p90
      - p95
      - p99

    而不是用文件级统计值做近似聚合。
    """
    detail_records: List[pd.DataFrame] = []

    for item in targets:
        task_dir = item["task_dir"]
        model_dir = item["model_dir"]
        xlsx_path = item["xlsx_path"]

        try:
            df = pd.read_excel(xlsx_path)

            if "token_count" not in df.columns:
                continue

            token_series = pd.to_numeric(df["token_count"], errors="coerce")

            valid_df = pd.DataFrame(
                {
                    "task": task_dir.name,
                    "model": model_dir.name,
                    "file": str(xlsx_path),
                    "file_name": xlsx_path.name,
                    "token_count": token_series,
                }
            ).dropna(subset=["token_count"])

            if not valid_df.empty:
                detail_records.append(valid_df)

        except Exception:
            continue

    if not detail_records:
        return pd.DataFrame(
            columns=["task", "model", "file", "file_name", "token_count"]
        )

    return pd.concat(detail_records, ignore_index=True)


def build_group_summary_from_details(
    detail_df: pd.DataFrame,
    file_summary_df: pd.DataFrame,
    group_cols: List[str],
) -> pd.DataFrame:
    """
    基于样本级 token_count 明细构建严格聚合统计。

    这里的 median / p90 / p95 / p99 都是基于所有样本级 token_count
    直接计算的，不再是文件级统计的近似值。
    """
    if detail_df.empty:
        return pd.DataFrame(columns=group_cols)

    processed_file_df = file_summary_df[file_summary_df["processed"] == True].copy()

    grouped_detail = detail_df.groupby(group_cols, dropna=False)

    token_summary = grouped_detail["token_count"].agg(
        valid_token_rows="count",
        mean_token="mean",
        median_token="median",
        min_token="min",
        max_token="max",
        sum_token="sum",
    ).reset_index()

    quantile_summary = (
        grouped_detail["token_count"]
        .quantile([0.90, 0.95, 0.99])
        .unstack()
        .rename(
            columns={
                0.90: "p90_token",
                0.95: "p95_token",
                0.99: "p99_token",
            }
        )
        .reset_index()
    )

    threshold_frames = []

    for label, threshold in TOKEN_THRESHOLDS.items():
        temp = detail_df.copy()
        temp[f"over_{label}_flag"] = temp["token_count"] >= threshold

        threshold_summary = (
            temp.groupby(group_cols, dropna=False)
            .agg(
                **{
                    f"over_{label}_count": (f"over_{label}_flag", "sum"),
                    f"over_{label}_rate": (f"over_{label}_flag", "mean"),
                }
            )
            .reset_index()
        )

        threshold_frames.append(threshold_summary)

    file_count_summary = (
        processed_file_df.groupby(group_cols, dropna=False)
        .agg(
            files=("file", "count"),
            rows=("rows", "sum"),
        )
        .reset_index()
    )

    summary = token_summary.merge(
        quantile_summary,
        on=group_cols,
        how="left",
    )

    for threshold_summary in threshold_frames:
        summary = summary.merge(
            threshold_summary,
            on=group_cols,
            how="left",
        )

    summary = summary.merge(
        file_count_summary,
        on=group_cols,
        how="left",
    )

    int_cols = [
        "valid_token_rows",
        "min_token",
        "max_token",
        "sum_token",
        "files",
        "rows",
        "over_4k_count",
        "over_8k_count",
        "over_16k_count",
    ]

    for col in int_cols:
        if col in summary.columns:
            summary[col] = summary[col].fillna(0).astype(int)

    ordered_cols = (
        group_cols
        + [
            "files",
            "rows",
            "valid_token_rows",
            "mean_token",
            "median_token",
            "p90_token",
            "p95_token",
            "p99_token",
            "min_token",
            "max_token",
            "sum_token",
            "over_4k_count",
            "over_8k_count",
            "over_16k_count",
            "over_4k_rate",
            "over_8k_rate",
            "over_16k_rate",
        ]
    )

    return summary[ordered_cols]


def format_summary_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    格式化输出：
      - token 数值列：四舍五入为整数
      - rate 比例列：转成百分数字符串，保留两位小数
    """
    formatted = df.copy()

    for col in TOKEN_VALUE_COLS:
        if col in formatted.columns:
            formatted[col] = pd.to_numeric(formatted[col], errors="coerce")
            formatted[col] = formatted[col].round(0).astype("Int64")

    for col in RATE_COLS:
        if col in formatted.columns:
            rate_values = pd.to_numeric(formatted[col], errors="coerce")
            formatted[col] = rate_values.apply(
                lambda x: "" if pd.isna(x) else f"{x * 100:.2f}%"
            )

    return formatted


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--root",
        type=str,
        default=".",
        help="根目录，默认当前目录",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="token_count_summary.xlsx",
        help="输出统计文件路径，默认 token_count_summary.xlsx",
    )
    args = parser.parse_args()

    root = Path(args.root).resolve()
    output_path = Path(args.output)

    if not root.exists():
        raise FileNotFoundError(f"根目录不存在: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"root 不是目录: {root}")

    print(f"根目录: {root}")

    targets = scan_target_excels(root)

    print(f"发现目标 Excel 文件数量: {len(targets)}")

    if not targets:
        print("未发现需要统计的 Excel 文件。")
        return

    file_records: List[Dict[str, Any]] = []

    for idx, item in enumerate(targets, start=1):
        task_dir = item["task_dir"]
        model_dir = item["model_dir"]
        xlsx_path = item["xlsx_path"]

        print(
            f"[{idx}/{len(targets)}] 统计: "
            f"{task_dir.name} / {model_dir.name} / {xlsx_path.name}"
        )

        record = summarize_excel(
            xlsx_path=xlsx_path,
            task_name=task_dir.name,
            model_name=model_dir.name,
        )

        file_records.append(record)

        if record["processed"]:
            print(
                f"  完成: rows={record['rows']}, "
                f"mean={record['mean_token']:.0f}, "
                f"p95={record['p95_token']:.0f}, "
                f"p99={record['p99_token']:.0f}, "
                f"max={record['max_token']}, "
                f"over_8k_rate={record['over_8k_rate'] * 100:.2f}%"
            )
        else:
            print(
                f"  跳过: reason={record['skipped_reason']}, "
                f"error={record['error']}"
            )

    file_summary_df = pd.DataFrame(file_records)

    print("")
    print("收集样本级 token_count 明细，用于严格计算聚合分位数...")
    detail_df = collect_token_details(targets=targets)

    model_summary_df = build_group_summary_from_details(
        detail_df=detail_df,
        file_summary_df=file_summary_df,
        group_cols=["model"],
    )

    task_summary_df = build_group_summary_from_details(
        detail_df=detail_df,
        file_summary_df=file_summary_df,
        group_cols=["task"],
    )

    task_model_summary_df = build_group_summary_from_details(
        detail_df=detail_df,
        file_summary_df=file_summary_df,
        group_cols=["task", "model"],
    )

    processed_count = int(file_summary_df["processed"].sum())
    skipped_count = len(file_summary_df) - processed_count

    print("")
    print("统计完成。")
    print(f"总 Excel 数: {len(file_summary_df)}")
    print(f"成功统计: {processed_count}")
    print(f"跳过/失败: {skipped_count}")
    print(f"样本级 token_count 明细行数: {len(detail_df)}")

    print(f"写出统计文件: {output_path}")

    file_summary_out = format_summary_df(file_summary_df)
    model_summary_out = format_summary_df(model_summary_df)
    task_summary_out = format_summary_df(task_summary_df)
    task_model_summary_out = format_summary_df(task_model_summary_df)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        file_summary_out.to_excel(writer, sheet_name="file_summary", index=False)
        model_summary_out.to_excel(writer, sheet_name="model_summary", index=False)
        task_summary_out.to_excel(writer, sheet_name="task_summary", index=False)
        task_model_summary_out.to_excel(
            writer,
            sheet_name="task_model_summary",
            index=False,
        )

    print(f"统计文件路径: {output_path.resolve()}")


if __name__ == "__main__":
    main()