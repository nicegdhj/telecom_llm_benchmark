# -*- coding: utf-8 -*-
"""
JSON 字段级评估器

支持对 JSON 结构化输出进行灵活的字段级评估：
1. 精确匹配字段（EM）
2. 值匹配字段（忽略键名，只比较值）
3. 部分匹配字段（包含关系）
4. ROUGE 匹配字段（基于分词的相似度，适合中文文本）
5. 嵌套结构支持
"""

import ast
import json
import re
import warnings
from typing import List, Dict, Any, Optional, Union

# 延迟导入 jieba 和 rouge，避免启动时的警告
_jieba = None
_Rouge = None


def _get_jieba():
    global _jieba
    if _jieba is None:
        warnings.filterwarnings(
            "ignore", message=".*pkg_resources is deprecated.*", category=UserWarning
        )
        import jieba

        _jieba = jieba
    return _jieba


def _get_rouge():
    global _Rouge
    if _Rouge is None:
        from rouge_chinese import Rouge

        _Rouge = Rouge
    return _Rouge


from ais_bench.benchmark.registry import ICL_EVALUATORS
from ais_bench.benchmark.openicl.icl_evaluator.icl_base_evaluator import BaseEvaluator


def safe_parse_json(text: str) -> Optional[Dict]:
    """安全解析 JSON，支持多种格式"""
    if not text:
        return None

    # 尝试直接解析
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # 尝试 ast.literal_eval，兼容 Python dict 字符串（单引号格式）
    try:
        result = ast.literal_eval(text)
        if isinstance(result, dict):
            return result
    except (ValueError, SyntaxError):
        pass

    # 尝试提取 JSON 块（可能被其他文本包裹）
    json_pattern = r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}"
    matches = re.findall(json_pattern, text, re.DOTALL)
    for match in matches:
        try:
            return json.loads(match)
        except json.JSONDecodeError:
            continue

    return None


def extract_all_values(obj: Any, values: set = None) -> set:
    """递归提取 JSON 中所有的值（非键）"""
    if values is None:
        values = set()

    if isinstance(obj, dict):
        for v in obj.values():
            extract_all_values(v, values)
    elif isinstance(obj, list):
        for item in obj:
            extract_all_values(item, values)
    elif isinstance(obj, str):
        parsed = safe_parse_json(obj)
        if parsed is not None and isinstance(parsed, (dict, list)):
            extract_all_values(parsed, values)
        else:
            values.add(obj.strip().lower())
    elif obj is not None:
        values.add(str(obj).strip().lower())

    return values


def compare_values_flexible(pred_val: Any, gold_val: Any) -> float:
    """灵活比较两个值，返回相似度 0-1"""
    if pred_val == gold_val:
        return 1.0

    pred_str = str(pred_val).strip().lower()
    gold_str = str(gold_val).strip().lower()

    if pred_str == gold_str:
        return 1.0

    # 部分包含
    if gold_str in pred_str or pred_str in gold_str:
        return 0.8

    return 0.0


def compare_values_rouge(pred_val: Any, gold_val: Any) -> float:
    """使用 ROUGE-L 评分中文文本相似度，返回 0-1

    适用于需要精确评估文本重合度的场景（如引用原文片段）
    """
    pred_str = str(pred_val).strip()
    gold_str = str(gold_val).strip()

    # 完全相等
    if pred_str == gold_str:
        return 1.0

    # 空字符串处理
    if not pred_str or not gold_str:
        return 0.0

    try:
        jieba = _get_jieba()
        Rouge = _get_rouge()

        # 分词
        pred_tokens = " ".join(jieba.cut(pred_str))
        gold_tokens = " ".join(jieba.cut(gold_str))

        # 避免空串错误
        if not pred_tokens.strip():
            pred_tokens = "__PRED__"
        if not gold_tokens.strip():
            gold_tokens = "__GOLD__"

        # 计算 ROUGE-L F1 分数
        rouge = Rouge()
        scores = rouge.get_scores([pred_tokens], [gold_tokens])
        rouge_l_f1 = scores[0]["rouge-l"]["f"]

        return float(rouge_l_f1)

    except Exception:
        # 如果 ROUGE 计算失败，回退到 flexible 模式
        return compare_values_flexible(pred_val, gold_val)


@ICL_EVALUATORS.register_module()
class JsonFieldEvaluator(BaseEvaluator):
    """
    JSON 字段级评估器

    配置示例：
    ```python
    evaluator=dict(
        type=JsonFieldEvaluator,
        field_config={
            "业务类别": {"match_type": "exact", "weight": 1.0},
            "信息提取": {"match_type": "value_only", "weight": 1.0},
        },
        default_match_type="exact",
    )
    ```

    match_type 选项：
    - "exact": 精确匹配（键和值都必须完全一致）
    - "value_only": 只比较值（忽略键名差异）
    - "contains": 包含匹配（pred 包含 gold）
    - "flexible": 灵活匹配（支持部分匹配）

    strict_mode：
    - False（默认）：各字段加权平均，支持部分得分
    - True：AND 逻辑，所有参评字段（weight > 0）都必须精确匹配才算正确，
      否则整个样本得 0 分。weight=0 的字段不参与评分。
    """

    def __init__(
        self,
        field_config: Dict[str, Dict] = None,
        default_match_type: str = "exact",
        return_details: bool = False,
        strict_mode: bool = False,
    ) -> None:
        super().__init__()
        self.field_config = field_config or {}
        self.default_match_type = default_match_type
        self.return_details = return_details
        self.strict_mode = strict_mode

    def _get_field_config(self, field_name: str) -> Dict:
        """获取字段配置，不存在则返回默认值"""
        return self.field_config.get(
            field_name, {"match_type": self.default_match_type, "weight": 1.0}
        )

    def _compare_field(self, pred_val: Any, gold_val: Any, match_type: str) -> float:
        """比较单个字段，返回分数 0-1"""

        if match_type == "exact":
            if pred_val == gold_val:
                return 1.0
            # 类型不同但字符串表示相同（如 3 vs "3"）视为匹配
            if str(pred_val).strip() == str(gold_val).strip():
                return 1.0
            return 0.0

        elif match_type == "value_only":
            # 对于嵌套结构，提取所有值进行比较
            if isinstance(gold_val, (dict, list)) and isinstance(
                pred_val, (dict, list)
            ):
                gold_values = extract_all_values(gold_val)
                pred_values = extract_all_values(pred_val)
                if not gold_values:
                    return 1.0 if not pred_values else 0.0
                overlap = len(gold_values & pred_values)
                return overlap / len(gold_values)
            else:
                return 1.0 if str(pred_val) == str(gold_val) else 0.0

        elif match_type == "contains":
            gold_str = str(gold_val)
            pred_str = str(pred_val)
            return 1.0 if gold_str in pred_str else 0.0

        elif match_type == "flexible":
            return compare_values_flexible(pred_val, gold_val)

        elif match_type == "rouge":
            return compare_values_rouge(pred_val, gold_val)

        else:
            # 默认精确匹配
            return 1.0 if pred_val == gold_val else 0.0

    def _evaluate_single(self, pred: str, gold: str) -> Dict[str, float]:
        """评估单个样本"""
        pred_json = safe_parse_json(pred)
        gold_json = safe_parse_json(gold)

        # 如果解析失败，使用字符串精确匹配
        if pred_json is None or gold_json is None:
            return {
                "accuracy": 1.0 if pred.strip() == gold.strip() else 0.0,
                "parse_success": 0.0,
            }

        # 计算各字段分数
        total_weight = 0.0
        weighted_score = 0.0
        field_scores = {}

        if isinstance(gold_json, dict):
            for field_name, gold_value in gold_json.items():
                config = self._get_field_config(field_name)
                match_type = config.get("match_type", self.default_match_type)
                weight = config.get("weight", 1.0)

                # strict_mode 下 weight=0 的字段不参与评分
                if self.strict_mode and weight == 0:
                    continue

                pred_value = (
                    pred_json.get(field_name) if isinstance(pred_json, dict) else None
                )

                if pred_value is None:
                    score = 0.0
                else:
                    score = self._compare_field(pred_value, gold_value, match_type)

                field_scores[field_name] = score
                weighted_score += score * weight
                total_weight += weight
        else:
            # 如果 gold_json 不是字典，将其作为一个整体进行比较
            match_type = self.default_match_type
            score = self._compare_field(pred_json, gold_json, match_type)
            result = {
                "accuracy": score,
                "parse_success": 1.0,
            }
            if self.return_details:
                result["field_scores"] = {"__overall__": score}
            return result

        if self.strict_mode:
            # AND 逻辑：所有参评字段都必须得 1.0，否则整体为 0
            overall_score = 1.0 if (field_scores and all(s == 1.0 for s in field_scores.values())) else 0.0
        else:
            overall_score = weighted_score / total_weight if total_weight > 0 else 0.0

        result = {
            "accuracy": overall_score,
            "parse_success": 1.0,
        }

        if self.return_details:
            result["field_scores"] = field_scores

        return result

    def score(self, predictions: List, references: List) -> Dict:
        """评估所有样本"""
        if len(predictions) != len(references):
            return {
                "error": f"predictions and references have different length. "
                f"len(predictions): {len(predictions)}, "
                f"len(references): {len(references)}"
            }

        total_accuracy = 0.0
        total_parse_success = 0.0
        all_field_scores = {}
        details = []

        for pred, gold in zip(predictions, references):
            result = self._evaluate_single(str(pred), str(gold))
            total_accuracy += result["accuracy"]
            total_parse_success += result.get("parse_success", 1.0)

            detail_item = {
                "pred": pred,
                "answer": gold,
            }
            if result["accuracy"] == 1.0:
                detail_item["eval_res"] = True
            elif result["accuracy"] == 0.0:
                detail_item["eval_res"] = False
            else:
                detail_item["eval_res"] = str(round(result["accuracy"] * 100, 2))

            detail_item["eval_details"] = None

            if self.return_details and "field_scores" in result:
                detail_item["eval_details"] = result["field_scores"]
                for field, score in result["field_scores"].items():
                    if field not in all_field_scores:
                        all_field_scores[field] = []
                    all_field_scores[field].append(score)

            details.append(detail_item)

        n = len(predictions)
        final_result = {
            "accuracy": (total_accuracy / n) * 100 if n > 0 else 0.0,
            "parse_success_rate": (total_parse_success / n) * 100 if n > 0 else 0.0,
            "details": details,
        }

        # 添加每个字段的平均分
        if all_field_scores:
            for field, scores in all_field_scores.items():
                final_result[f"field_{field}"] = (sum(scores) / len(scores)) * 100

        return final_result


@ICL_EVALUATORS.register_module()
class JsonValueMatchEvaluator(JsonFieldEvaluator):
    """
    JSON 值匹配评估器（简化版）

    默认行为：
    - 第一层字段使用精确匹配
    - 嵌套结构使用值匹配（忽略键名）

    适用于 task_1 这类场景：业务类别精确匹配，信息提取只比较值
    """

    def __init__(
        self,
        exact_fields: List[str] = None,
        value_only_fields: List[str] = None,
        **kwargs,
    ) -> None:
        # 构建 field_config
        field_config = {}

        for field in exact_fields or []:
            field_config[field] = {"match_type": "exact", "weight": 1.0}

        for field in value_only_fields or []:
            field_config[field] = {"match_type": "value_only", "weight": 1.0}

        super().__init__(
            field_config=field_config, default_match_type="exact", **kwargs
        )


# 为 task_1 类型任务预置的评估器
@ICL_EVALUATORS.register_module()
class BusinessClassificationEvaluator(JsonFieldEvaluator):
    """
    业务分类任务评估器

    专门用于评估包含 "业务类别" 和 "信息提取" 的 JSON 输出：
    - 业务类别：精确匹配
    - 信息提取：值匹配（忽略键名差异）
    """

    def __init__(self, **kwargs) -> None:
        super().__init__(
            field_config={
                "业务类别": {"match_type": "exact", "weight": 1.0},
                "信息提取": {"match_type": "value_only", "weight": 1.0},
            },
            default_match_type="flexible",
            return_details=True,
            **kwargs,
        )

from ais_bench.benchmark.openicl.icl_evaluator.llm_judge_evaluator import LLMJudgeEvaluator
from ais_bench.benchmark.utils.logging.logger import AISLogger

LLM_FALLBACK_PROMPT = """
# Role
你是一个高精度的自然语言处理评分专家，擅长评估“模型提取结果 (Pre)”与“标准答案 (Gold)”之间的语义一致性。

# Task
对比 Pre 和 Gold 中的信息，判断两者是否指向同一实体或表达完全相同的核心意思。即使字面不完全一致，只要语义等价即视为正确。

# Evaluation Criteria
1. **语义对齐 (给 1 分)**：
   - 实体简称与全称：如“浙江”与“浙江省”。
   - 同义词与多语言：如“计算机”与“电脑”。
   - 格式与符号干扰：存在多余空格、大小写差异、或合理的单位省略（如“100元”与“100”）。
2. **不匹配或信息缺失 (给 0 分)**：
   - 核心信息冲突或关键限定词丢失，导致语义范围扩大或改变。
3. **严格打分**：仅允许输出 0 或 1，禁止输出 0.5 等中间值。

# Output Format
必须严格输出合法的 JSON 格式，不要包含任何 Markdown 标记（如 ```json），格式如下：
{{
  "score": <0或1的整数>,
  "reason": "<简短说明判分理由>"
}}

Gold: {reference}
Pre: {prediction}
"""

@ICL_EVALUATORS.register_module()
class JsonWithLLMFallbackEvaluator(JsonFieldEvaluator):
    """
    在 JsonFieldEvaluator 基础上，仅对 fault_location 字段进行 LLM 语义兜底。
    总体评分框架与 JsonFieldEvaluator 完全保持一致（支持 strict_mode / weight）。
    """

    LLM_FALLBACK_FIELD = "fault_location"

    def __init__(self, **kwargs):
        kwargs["default_match_type"] = "exact"
        kwargs["return_details"] = True
        super().__init__(**kwargs)
        self._llm_evaluator = None
        self.logger = AISLogger()

    @property
    def llm_evaluator(self):
        if self._llm_evaluator is None:
            self._llm_evaluator = LLMJudgeEvaluator()
        return self._llm_evaluator

    def _extract_field_value(self, raw: str, field: str):
        """从原始预测/标准答案字符串中提取指定字段的值"""
        parsed = safe_parse_json(str(raw))
        if isinstance(parsed, dict):
            return parsed.get(field)
        return None

    def _recompute_sample_accuracy(self, field_scores: dict) -> float:
        """根据 field_scores 重新计算样本级准确率（与 _evaluate_single 保持一致）"""
        if not field_scores:
            return 0.0
        if self.strict_mode:
            return 1.0 if all(s == 1.0 for s in field_scores.values()) else 0.0
        total_weight = 0.0
        weighted_score = 0.0
        for field_name, score in field_scores.items():
            config = self._get_field_config(field_name)
            weight = config.get("weight", 1.0)
            if self.strict_mode and weight == 0:
                continue
            weighted_score += score * weight
            total_weight += weight
        return weighted_score / total_weight if total_weight > 0 else 0.0

    def _call_llm_batch(self, prompts: List[str]) -> List[str]:
        """批量调用 LLM，返回原始输出列表"""
        if not prompts or self.llm_evaluator.model is None:
            return []
        _m = self.llm_evaluator.model
        self.logger.info(
            f"[LLM Debug] URL={getattr(_m, 'url', 'N/A')} "
            f"model={getattr(_m, 'model', 'N/A')} "
            f"headers_keys={list(getattr(_m, 'headers', {}).keys())}"
        )
        if getattr(_m, 'is_api', False):
            import asyncio
            from ais_bench.benchmark.models.output import RequestOutput
            import aiohttp
            async def _run():
                async with aiohttp.ClientSession(trust_env=True) as session:
                    outputs = [RequestOutput(False) for _ in prompts]
                    tasks = [
                        _m.generate(input_data=p, max_out_len=512, output=out, session=session)
                        for p, out in zip(prompts, outputs)
                    ]
                    await asyncio.gather(*tasks)
                    for i, out in enumerate(outputs):
                        self.logger.info(
                            f"[LLM API] idx={i} success={out.success} "
                            f"error={out.error_info!r} content_len={len(out.content)}"
                        )
                    return [out.content for out in outputs]
            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
            return loop.run_until_complete(_run())
        else:
            return _m.generate(prompts, max_out_len=512)

    def _parse_llm_score(self, judge_output: str) -> float:
        """解析 LLM 返回的 JSON，提取 score 字段"""
        if not judge_output:
            return 0.0
        clean = str(judge_output).strip()
        clean = re.sub(r'```json\s*', '', clean, flags=re.IGNORECASE)
        clean = re.sub(r'```\s*', '', clean).strip()
        try:
            return float(json.loads(clean).get("score", 0))
        except Exception as e:
            self.logger.warning(f"[LLM Parse] 解析失败 (给0分): {e} | 原文: {clean}")
            return 0.0

    def score(self, predictions: List, references: List) -> Dict:
        self.logger.info(
            f"========== 开始 JsonWithLLMFallbackEvaluator 评估，共 {len(predictions)} 条数据 =========="
        )
        # ① 先用 JsonFieldEvaluator 进行全量 Exact Match 评估
        base_res = super().score(predictions, references)
        details = base_res.get("details", [])

        if self.llm_evaluator.model is None:
            self.logger.info("========== 评估结束（无 LLM 模型，使用纯规则结果）==========")
            return base_res

        # ② 找出 fault_location 字段得分为 0 的样本，准备 LLM 兜底
        fallback_indices = []
        prompts = []
        for i, detail in enumerate(details):
            field_scores = detail.get("eval_details") or {}
            loc_score = field_scores.get(self.LLM_FALLBACK_FIELD)
            if loc_score is not None and loc_score < 1.0:
                pred_val = self._extract_field_value(predictions[i], self.LLM_FALLBACK_FIELD)
                gold_val = self._extract_field_value(references[i], self.LLM_FALLBACK_FIELD)
                self.logger.info(
                    f"[Fallback Triggered] 第 {i} 条数据 fault_location Exact Match 失败。\n"
                    f" - Pred: {pred_val}\n"
                    f" - Gold: {gold_val}"
                )
                fallback_indices.append(i)
                prompts.append(LLM_FALLBACK_PROMPT.format(
                    reference=str(gold_val), prediction=str(pred_val)
                ))
            else:
                self.logger.info(f"[Exact Match] 第 {i} 条数据 fault_location 匹配成功（score={loc_score}）")

        # ③ 批量调 LLM，只针对 fault_location
        if prompts:
            self.logger.info(f"[LLM Run] 共 {len(prompts)} 条 fault_location 进入 LLM 兜底判分...")
            judgements = self._call_llm_batch(prompts)

            for list_pos, idx in enumerate(fallback_indices):
                judge_output = judgements[list_pos] if list_pos < len(judgements) else ""
                llm_score = self._parse_llm_score(judge_output)
                self.logger.info(
                    f"--- 第 {idx} 条 fault_location LLM 兜底结果 ---\n"
                    f"原始输出: {judge_output}\n"
                    f"解析得分: {llm_score}"
                )
                # 更新该样本的 fault_location 字段分数
                field_scores = dict(details[idx].get("eval_details") or {})
                field_scores[self.LLM_FALLBACK_FIELD] = llm_score
                details[idx]["eval_details"] = field_scores
                details[idx]["llm_judge_output"] = judge_output

                # ④ 用更新后的 field_scores 重新计算样本级 accuracy（严格模式 AND 逻辑）
                new_accuracy = self._recompute_sample_accuracy(field_scores)
                details[idx]["eval_res"] = True if new_accuracy == 1.0 else False

        # ⑤ 重新汇总，保持与 JsonFieldEvaluator 一致的输出格式
        total_accuracy = 0.0
        all_field_scores: dict = {}
        for detail in details:
            acc = 1.0 if detail.get("eval_res") is True else 0.0
            total_accuracy += acc
            for field, fscore in (detail.get("eval_details") or {}).items():
                all_field_scores.setdefault(field, []).append(fscore)

        n = len(predictions)
        base_res["accuracy"] = (total_accuracy / n) * 100 if n > 0 else 0.0
        base_res["details"] = details
        for field, scores in all_field_scores.items():
            base_res[f"field_{field}"] = (sum(scores) / len(scores)) * 100

        self.logger.info(f"========== 评估结束，总体准确率为: {base_res['accuracy']}% ==========")
        return base_res
