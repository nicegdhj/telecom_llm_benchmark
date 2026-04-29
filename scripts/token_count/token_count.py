# -*- coding: utf-8 -*-
"""
为 xlsx 文件中的 prediction 列新增/覆盖 token_count 列。

支持两种模式：

1. 单文件模式：
   python token_count.py --input your_file.xlsx

2. 批处理模式：
   python token_count.py --root .

批处理目录结构假设：
./
  ├── tokenizers/
  │   ├── qwen3/
  │   └── qwen3.5/
  ├── token_count.py
  ├── AIME-2025/
  │   ├── qwen3_32b_think/
  │   │   └── result.xlsx
  │   ├── qwen3_5_xxx/
  │   │   └── result.xlsx
  │   └── ...
  └── ...

处理范围：
  批处理时只处理 ./任务文件夹/模型文件夹/*.xlsx
  不处理根目录下的 xlsx
  不递归处理更深层目录

tokenizer 自动选择规则：
  - 模型文件夹名包含 qwen3_5 时，使用 ./tokenizers/qwen3.5
  - 其他情况默认使用 ./tokenizers/qwen3

用法：
  python token_count.py --input your_file.xlsx
  python token_count.py --root .
  python token_count.py --root . --log token_count_log.xlsx
"""

import argparse
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
from transformers import AutoTokenizer


IGNORED_DIRS = {
    "tokenizers",
    "__pycache__",
    ".git",
    ".vscode",
    ".idea",
}


DEFAULT_TOKENIZER_PATH = "./tokenizers/qwen3"


# 后续新增特殊模型时，只需要在这里追加规则。
# 规则按顺序匹配，先匹配到的优先。
TOKENIZER_RULES = [
    {
        "name": "qwen3.5",
        "keywords": [
            "qwen3_5",
            "qwen3.5",
        ],
        "path": "./tokenizers/qwen3.5",
    },
    {
        "name": "qwen3",
        "keywords": [
            "qwen3",
            "qwen_3",
        ],
        "path": "./tokenizers/qwen3",
    },
]


def count_tokens(text, tokenizer) -> int:
    """统计单条文本的 token 数。"""
    if pd.isna(text):
        text = ""
    text = str(text)
    return len(tokenizer.encode(text, add_special_tokens=False))


def normalize_name(name: str) -> str:
    """
    标准化模型目录名，降低大小写差异影响。
    """
    return name.lower().strip()


def resolve_tokenizer_path(model_name: Optional[str]) -> Tuple[Path, str]:
    """
    根据模型文件夹名选择 tokenizer。

    参数：
      model_name:
        - 批处理模式下：二级模型目录名，例如 qwen3_32b_think
        - 单文件模式下：如果无法推断，可为 None

    返回：
      (tokenizer_path, tokenizer_rule_name)
    """
    if model_name:
        normalized_model_name = normalize_name(model_name)

        for rule in TOKENIZER_RULES:
            for keyword in rule["keywords"]:
                if keyword.lower() in normalized_model_name:
                    return Path(rule["path"]), rule["name"]

    return Path(DEFAULT_TOKENIZER_PATH), "default_qwen3"


def load_tokenizer(tokenizer_path: Path, tokenizer_cache: Dict[str, Any]):
    """
    加载 tokenizer，并做缓存，避免批处理时重复加载。
    """
    tokenizer_key = str(tokenizer_path.resolve())

    if tokenizer_key in tokenizer_cache:
        return tokenizer_cache[tokenizer_key]

    if not tokenizer_path.exists():
        raise FileNotFoundError(f"tokenizer 路径不存在: {tokenizer_path}")

    print(f"加载 tokenizer: {tokenizer_path}")

    tokenizer = AutoTokenizer.from_pretrained(
        tokenizer_path,
        trust_remote_code=True,
        local_files_only=True,
    )

    tokenizer_cache[tokenizer_key] = tokenizer
    return tokenizer


def is_task_dir(path: Path) -> bool:
    """判断是否应作为任务目录处理。"""
    return path.is_dir() and path.name not in IGNORED_DIRS


def scan_target_excels(root: Path) -> List[Dict[str, Path]]:
    """
    扫描目标 Excel 文件。

    只扫描：
      ./任务文件夹/模型文件夹/*.xlsx

    不扫描：
      ./根目录/*.xlsx
      ./任务文件夹/模型文件夹/更深层目录/*.xlsx
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


def process_excel(
    xlsx_path: Path,
    tokenizer,
    task_name: Optional[str] = None,
    model_name: Optional[str] = None,
    tokenizer_name: Optional[str] = None,
    tokenizer_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    处理单个 Excel 文件。

    若包含 prediction 列：
      - 新增/覆盖 token_count 列
      - 原地写回

    若不包含 prediction 列：
      - 跳过
    """
    record: Dict[str, Any] = {
        "task": task_name,
        "model": model_name,
        "file": str(xlsx_path),
        "file_name": xlsx_path.name,
        "tokenizer_name": tokenizer_name,
        "tokenizer_path": str(tokenizer_path) if tokenizer_path else None,
        "processed": False,
        "has_prediction": False,
        "rows": None,
        "skipped_reason": None,
        "error": None,
    }

    try:
        if not xlsx_path.exists():
            record["skipped_reason"] = "file_not_found"
            record["error"] = f"文件不存在: {xlsx_path}"
            return record

        if xlsx_path.suffix.lower() != ".xlsx":
            record["skipped_reason"] = "not_xlsx"
            return record

        df = pd.read_excel(xlsx_path)
        record["rows"] = len(df)

        if "prediction" not in df.columns:
            record["skipped_reason"] = "missing_prediction_column"
            return record

        record["has_prediction"] = True

        df["token_count"] = df["prediction"].apply(
            lambda x: count_tokens(x, tokenizer)
        )

        df.to_excel(xlsx_path, index=False)

        record["processed"] = True
        return record

    except Exception as e:
        record["skipped_reason"] = "error"
        record["error"] = repr(e)
        return record


def infer_task_and_model_from_input(input_path: Path) -> Tuple[Optional[str], Optional[str]]:
    """
    单文件模式下，尝试从路径推断 task / model。

    例如：
      ./AIME-2025/qwen3_32b_think/result.xlsx
    推断为：
      task=AIME-2025
      model=qwen3_32b_think

    如果路径层级不足，则返回 None。
    """
    parent = input_path.parent
    grandparent = parent.parent

    if parent.name and grandparent.name:
        return grandparent.name, parent.name

    return None, None


def run_single_file_mode(args):
    """
    单文件模式：
      python token_count.py --input your_file.xlsx

    tokenizer 选择：
      1. 如果传入 --model，则强制使用该 tokenizer 路径
      2. 否则尝试根据 input 的父目录名，也就是模型目录名自动选择
    """
    input_path = Path(args.input)

    task_name, model_name = infer_task_and_model_from_input(input_path)

    if args.model:
        tokenizer_path = Path(args.model)
        tokenizer_rule_name = "manual"
    else:
        tokenizer_path, tokenizer_rule_name = resolve_tokenizer_path(model_name)

    tokenizer_cache: Dict[str, Any] = {}
    tokenizer = load_tokenizer(tokenizer_path, tokenizer_cache)

    record = process_excel(
        xlsx_path=input_path,
        tokenizer=tokenizer,
        task_name=task_name,
        model_name=model_name,
        tokenizer_name=tokenizer_rule_name,
        tokenizer_path=tokenizer_path,
    )

    if record["processed"]:
        print("完成。")
        print(f"已更新文件: {input_path.resolve()}")
        print(f"使用 tokenizer: {tokenizer_path}")
    else:
        print(
            f"跳过/失败: reason={record['skipped_reason']}, "
            f"error={record['error']}"
        )


def run_batch_mode(args):
    """
    批处理模式：
      python token_count.py --root .

    根据 ./任务文件夹/模型文件夹/*.xlsx 中的模型文件夹名自动选择 tokenizer。
    """
    root = Path(args.root).resolve()
    log_path = Path(args.log)

    if not root.exists():
        raise FileNotFoundError(f"根目录不存在: {root}")

    if not root.is_dir():
        raise NotADirectoryError(f"root 不是目录: {root}")

    print(f"根目录: {root}")

    targets = scan_target_excels(root)

    print(f"发现目标 Excel 文件数量: {len(targets)}")

    if not targets:
        print("未发现需要处理的 Excel 文件。")
        return

    tokenizer_cache: Dict[str, Any] = {}
    log_records: List[Dict[str, Any]] = []

    for idx, item in enumerate(targets, start=1):
        task_dir = item["task_dir"]
        model_dir = item["model_dir"]
        xlsx_path = item["xlsx_path"]

        tokenizer_path, tokenizer_rule_name = resolve_tokenizer_path(model_dir.name)
        tokenizer = load_tokenizer(tokenizer_path, tokenizer_cache)

        print(
            f"[{idx}/{len(targets)}] 处理: "
            f"{task_dir.name} / {model_dir.name} / {xlsx_path.name}"
        )

        record = process_excel(
            xlsx_path=xlsx_path,
            tokenizer=tokenizer,
            task_name=task_dir.name,
            model_name=model_dir.name,
            tokenizer_name=tokenizer_rule_name,
            tokenizer_path=tokenizer_path,
        )

        log_records.append(record)

        if record["processed"]:
            print(f"  完成: rows={record['rows']}")
        else:
            print(
                f"  跳过/失败: reason={record['skipped_reason']}, "
                f"error={record['error']}"
            )

    log_df = pd.DataFrame(log_records)

    processed_count = int(log_df["processed"].sum())
    skipped_count = len(log_df) - processed_count

    print("")
    print("token_count 生成完成。")
    print(f"总 Excel 数: {len(log_df)}")
    print(f"成功处理: {processed_count}")
    print(f"跳过/失败: {skipped_count}")

    print(f"写出处理日志: {log_path}")
    log_df.to_excel(log_path, index=False)
    print(f"处理日志路径: {log_path.resolve()}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--input",
        type=str,
        default=None,
        help="单文件模式：目标 xlsx 文件路径",
    )
    parser.add_argument(
        "--root",
        type=str,
        default=".",
        help="批处理模式：根目录，默认当前目录",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help=(
            "手动指定 tokenizer 路径。"
            "如果不指定，则根据模型文件夹名自动选择。"
        ),
    )
    parser.add_argument(
        "--log",
        type=str,
        default="token_count_log.xlsx",
        help="批处理模式下的处理日志文件路径，默认 token_count_log.xlsx",
    )

    args = parser.parse_args()

    if args.input:
        run_single_file_mode(args)
    else:
        run_batch_mode(args)


if __name__ == "__main__":
    main()