"""
ExamDataset — 通用考试数据集加载器

数据文件结构（benchmark/data/exam/）：
    每张试卷对应一个 JSON 文件，文件名即试卷标识（subdivision）。

JSON 文件格式（顶层按题型分区）：
    {
        "multiple_choice": [
            {
                "id":        "1",
                "question":  "题目文本（选项已嵌入）",
                "answer":    "B",
                "score":     "5",
                "has_image": false,
                "need_plot": false,
                "plot_desc": ""
            },
            ...
        ],
        "fill_blank": [ ... ],
        "subjective":  [ ... ]
    }

加载后每条样本字段：
    question_raw (str)  – 原始题目文本
    question     (str)  – 题目 + 题型专属指令（用于模型推理输入）
    answer       (str)  – 标准答案
    type         (str)  – 题型：multiple_choice / fill_blank / subjective
    score        (float)– 本题满分（数值化）
    has_image    (bool) – 是否含题目图片
    need_plot    (bool) – 是否要求绘图作答
    plot_desc    (str)  – 图片/绘图描述
    subdivision  (str)  – 试卷标识（文件名，无后缀）
"""

import json
import os
import re

from datasets import Dataset

from ais_bench.benchmark.registry import LOAD_DATASET
from ais_bench.benchmark.datasets.base import BaseDataset
from ais_bench.benchmark.utils.logging.logger import AISLogger

logger = AISLogger()

# 支持的题型键名（JSON 顶层 key）
QUESTION_TYPES = ("multiple_choice", "fill_blank", "subjective")

# ── 题型专属输出约束指令 ────────────────────────────────────────
# 在数据加载阶段拼接到题目末尾，严格约束模型输出格式。
# 禁止在配置文件中使用全局统一 prompt，所有格式约束在此集中管理。
_PROMPT_SUFFIX = {
    "multiple_choice": (
        "\n\n【作答要求】请直接给出本题的正确选项字母。若有多个空，请按顺序给出对应字母（如 A 或 CD）。"
        "不要输出任何解释、标点或其他内容。"
    ),
    "fill_blank": (
        "\n\n【作答要求】请直接给出填空处的最终答案，"
        "不要包含解题过程或其他解释内容。"
    ),
    "subjective": (
        "\n\n【作答要求】请给出详细的解答过程和最终结论。"
    ),
}


def _parse_score(raw) -> float:
    """将 score 字段解析为浮点数。

    支持：
        - 纯数字字符串 "5" → 5.0
        - 带单位字符串 "5分" → 5.0
        - 数值类型 5 / 5.0 → 5.0
    默认返回 1.0（如解析失败）。
    """
    if raw is None:
        return 1.0
    if isinstance(raw, (int, float)):
        return float(raw)
    match = re.search(r"([\d.]+)", str(raw))
    if match:
        return float(match.group(1))
    return 1.0


def _normalize_answer(raw) -> str:
    """将 answer 字段规范化为字符串。

    兼容两种格式：
        - 字符串："A" / "AB" / "长文本答案..."  →  原样返回（去首尾空白）
        - 字典（多空题）：{"3": "D", "4": "C"}   →  按 key 数字序拼接 values → "DC"

    例如：
        {"9": "D", "10": "B", "11": "C"} → "DBC"
        "A"  → "A"
    """
    if raw is None:
        return ""
    if isinstance(raw, dict):
        # 按 key 的数字值升序排列，拼接所有 value
        try:
            sorted_values = [
                str(v).strip()
                for _, v in sorted(raw.items(), key=lambda kv: int(kv[0]))
            ]
        except (ValueError, TypeError):
            # key 不能转为整数时，按字典默认顺序
            sorted_values = [str(v).strip() for v in raw.values()]
        return "".join(sorted_values)
    return str(raw).strip()


@LOAD_DATASET.register_module()
class ExamDataset(BaseDataset):
    """通用考试数据集，支持选择题、填空题和主观题的混合加载。

    Args:
        path (str): 数据根目录（如 ``data/exam``）。
        name (str | None): 试卷文件名（无后缀，如 ``exam_858_2023``）。
            若为 None，则加载 path 下所有 JSON 文件。
        **kwargs: 传递给父类的额外参数。

    Returns:
        Dataset: HuggingFace Dataset，包含字段
        ``question``, ``answer``, ``type``, ``score``,
        ``has_image``, ``need_plot``, ``plot_desc``, ``subdivision``。
    """

    @staticmethod
    def load(path: str, name: str = None, **kwargs) -> Dataset:
        raw_data = []

        # 收集待处理的文件列表
        if name:
            fname = name if name.endswith(".json") else f"{name}.json"
            file_paths = [os.path.join(path, fname)]
        else:
            # 加载目录下所有 JSON 文件
            try:
                all_files = sorted(os.listdir(path))
            except FileNotFoundError:
                logger.warning(f"[ExamDataset] path does not exist: {path}")
                return Dataset.from_list([])
            file_paths = [
                os.path.join(path, f) for f in all_files if f.endswith(".json")
            ]

        for file_path in file_paths:
            if not os.path.exists(file_path):
                logger.warning(f"[ExamDataset] file not found: {file_path}")
                continue

            subdivision = os.path.splitext(os.path.basename(file_path))[0]

            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
            except Exception as e:
                logger.warning(f"[ExamDataset] Failed to load {file_path}: {e}")
                continue

            if not isinstance(data, dict):
                logger.warning(
                    f"[ExamDataset] Unexpected format in {file_path} "
                    "(expected a dict with question-type keys), skipping."
                )
                continue

            for q_type in QUESTION_TYPES:
                items = data.get(q_type, [])
                if not isinstance(items, list):
                    logger.warning(
                        f"[ExamDataset] '{q_type}' in {file_path} is not a list, skipping."
                    )
                    continue

                for item in items:
                    question_raw = item.get("question", "").strip()
                    answer = _normalize_answer(item.get("answer"))

                    has_image = bool(item.get("has_image", False))
                    need_plot = bool(item.get("need_plot", False))

                    if has_image or need_plot:
                        logger.debug(
                            f"[ExamDataset] Skipping question with image/plot requirement in {file_path}"
                        )
                        continue

                    if not question_raw:
                        logger.debug(
                            f"[ExamDataset] Skipping empty question in {file_path} ({q_type})"
                        )
                        continue

                    # 拼接题型专属输出约束指令，在加载阶段完成动态 prompt 构建，
                    # 无需在配置文件中为不同题型编写不同模板。
                    prompt_suffix = _PROMPT_SUFFIX.get(q_type, "")
                    question_prompt = question_raw + prompt_suffix

                    raw_data.append(
                        {
                            "question_raw": question_raw,       # 原始题目文本（备用）
                            "question": question_prompt,        # 最终推理输入（含约束指令）
                            "answer": answer,
                            "type": q_type,
                            "score": _parse_score(item.get("score")),
                            "has_image": has_image,
                            "need_plot": need_plot,
                            "plot_desc": item.get("plot_desc", ""),
                            "subdivision": subdivision,
                        }
                    )

        if not raw_data:
            logger.warning(
                f"[ExamDataset] No data loaded from path='{path}', name='{name}'."
            )

        logger.info(
            f"[ExamDataset] Loaded {len(raw_data)} questions from path='{path}', name='{name}'."
        )
        return Dataset.from_list(raw_data)
