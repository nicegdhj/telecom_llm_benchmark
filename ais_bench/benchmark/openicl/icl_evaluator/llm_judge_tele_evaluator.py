# -*- coding: utf-8 -*-
# @Time    : 2026/4/23 14:14
# @Author  : jia
# @File    : llm_judge_tele_evaluator.py
# @Desc    :


import re
from typing import List

from datasets import Dataset

from ais_bench.benchmark.registry import ICL_EVALUATORS
from ais_bench.benchmark.utils.postprocess.model_postprocessors import extract_non_reasoning_content
from ais_bench.benchmark.openicl.icl_evaluator.llm_judge_evaluator import LLMJudgeEvaluator

TELECOM_JUDGE_PROMPT_TEMPLATE = """
# Role: 通信领域AI模型知识评估专家

## Profile:
- Description: 你是一名具有通信行业背景的AI模型输出质量评估专家，熟悉通信协议（如5G NR、LTE、IMS、SDN/NFV等）、网络规划、无线接入、核心网、传输网等专业知识。你的任务是评估候选模型的回答与参考答案（Ground Truth）之间的知识一致性，判断模型是否从训练数据中有效学习到了正确的通信领域知识。

## Skills:
1. 能准确判断候选答案是否覆盖了参考答案中的核心通信知识点和事实。
2. 擅长识别通信场景中的幻觉：如捏造不存在的协议参数、错误的技术规格（频段、时隙、编码方式等）、虚构的标准条款。
3. 能包容合理的同义替换或不同但正确的表述方式，而不拘泥于逐字匹配。
4. 能识别通信术语使用是否规范（如区分"上行/下行"、"信道/载波"等易混淆概念）。

##目标
- 给定一个通信行业的**专业问题**，一个**标准答案**，一个**模型答案**
- 基于**标准答案**，给出你对于**模型答案**的评分
- 评分需要分3个维度：核心事实一致性、专业准确性、以及表述完整性，评分维度如下：

## 评估维度（每个评估项满分10分，精确到1分）:

### 维度1：核心事实一致性
评估候选答案与参考答案在核心知识点上的吻合程度。

- **10分**：候选答案完整覆盖参考答案中所有核心知识点，无事实冲突，即使换了表述本质完全一致。
- **8分**：涵盖绝大部分核心知识点，存在极细微遗漏或措辞差异，不影响技术理解。
- **6分**：涵盖超过一半的核心知识点，无严重事实冲突，但有明显遗漏。
- **4分**：遗漏大部分核心知识点，或存在明显事实冲突（如错误的数值/参数/协议名称）。
- **2分**：与参考答案完全相悖，或提供了与问题无关的内容。
- **0分**：完全未作答，或输出为乱码/无意义内容。

### 维度2：专业准确性
评估候选答案中通信专业术语和技术细节的正确性。

- **10分**：术语使用规范，技术参数（频率、时隙、编码、接口名称等）完全正确，无捏造内容。
- **8分**：术语基本正确，偶有细微的专业表述不够严谨但不影响理解。
- **6分**：大部分术语正确，但有个别术语使用不当或技术细节模糊。
- **4分**：存在明显的术语混淆或错误技术规格（如错误的协议版本、参数量级）。
- **2分**：大量术语错误或存在严重的技术事实错误（如把上行和下行混淆）。
- **0分**：专业内容完全错误或充斥捏造的技术描述（幻觉严重）。

### 维度3：表述完整性
评估答案的内容完整程度和语言表达质量。

- **10分**：内容结构清晰，表述流畅，覆盖参考答案的逻辑层次，有合理扩展且无误。
- **8分**：内容较完整，结构清晰，表述准确，存在少量遗漏但不影响整体。
- **6分**：内容基本完整，但有明显遗漏或表述略显啰嗦/生硬。
- **4分**：内容存在较多遗漏，或结构混乱，影响理解。
- **2分**：内容严重缺失、答案被截断或逻辑支离破碎。
- **0分**：完全无法阅读或表述完全错乱。

## 用户问题（指令+附加信息）:
{question}

## 参考答案（Ground Truth）:
{reference_output}

## 候选模型输出（Candidate）:
{candidate_output}

## 要求
1.请先按照评估维度思考和判断，给出打分理由后，再按该评估项下打分细则进行打分
2.按评估项逐一进行判断和打分，不要一次性进行

## 输出格式:
- 直接以JSON对象输出，不要添加任何markdown代码块或多余前缀/后缀。输出必须以 {{ 开始，以 }} 结束。
- score_1 为第一个维度的评估分数，evaluate_1 为第一评估维度的原因，依次类推

输出示例：
{{
  "核心事实一致性": "候选答案覆盖了参考答案中关于5G NR帧结构的主要知识点，xxx", 
  "核心事实一致性得分": 8.0, 
  "专业准确性评价": "xxx", 
  "专业准确性得分": 6.0, 
  "表述完整性评价": "xxx", 
  "表述完整性得分": 8.0, 
}}

"""

@ICL_EVALUATORS.register_module()
class TelecomLLMJudgeEvaluator(LLMJudgeEvaluator):
    """通信领域 LLM 打分评估器。

    使用通信专域 prompt，输出 JSON 格式（score/evaluation/hallucination），
    最终指标与 LLMJudgeEvaluator 兼容，并额外输出 hallucination_rate。
    """

    MAX_SCORE = 10.0

    # 新格式三维度字段名
    _DIM_SCORE_KEYS = ["核心事实一致性得分", "专业准确性得分", "表述完整性得分"]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def score(self, predictions: List, references: List, test_set: Dataset = None) -> dict:
        if not self.model:
            return {'error': 'Model instance could not be created for TelecomLLMJudgeEvaluator.'}

        prompts = []
        for i, (pred, ref) in enumerate(zip(predictions, references)):
            question = test_set[i].get('input', '') if test_set and i < len(test_set) else ''
            prompt = TELECOM_JUDGE_PROMPT_TEMPLATE.format(
                question=question,
                reference_output=ref,
                candidate_output=pred,
            )
            prompts.append(prompt)

        self.logger.info(
            f"[TelecomLLMJudge] 打分模型: type={type(self.model).__name__}, "
            f"url={getattr(self.model, 'url', 'N/A')}, "
            f"model={getattr(self.model, 'model', 'N/A')}, "
            f"共 {len(prompts)} 条待评分"
        )

        max_out_len = 512
        if getattr(self.model, 'is_api', False):
            import asyncio
            from ais_bench.benchmark.models.output import RequestOutput
            import aiohttp

            async def _run_api_inference():
                async with aiohttp.ClientSession(trust_env=True) as session:
                    outputs = [RequestOutput(False) for _ in prompts]
                    tasks = [
                        self.model.generate(
                            input_data=prompt,
                            max_out_len=max_out_len,
                            output=output,
                            session=session,
                        )
                        for prompt, output in zip(prompts, outputs)
                    ]
                    await asyncio.gather(*tasks)
                    return [out.content for out in outputs]

            try:
                loop = asyncio.get_event_loop()
            except RuntimeError:
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

            if loop.is_running():
                import nest_asyncio
                nest_asyncio.apply()
                judgements = loop.run_until_complete(_run_api_inference())
            else:
                judgements = loop.run_until_complete(_run_api_inference())
        else:
            judgements = self.model.generate(prompts, max_out_len=max_out_len)

        import json as _json

        details = []
        for i, (pred, ref, judge_output) in enumerate(zip(predictions, references, judgements)):
            if judge_output is None or str(judge_output).strip() == '':
                self.logger.warning(
                    f"Empty judge output at index {i}, score set to None. "
                    f"Prompt: {prompts[i][:100]}..."
                )
                details.append({
                    'prompt': prompts[i],
                    'pred': pred,
                    'refr': ref,
                    'judge_output': '',
                    'llm_score': None,
                    'max_score': self.MAX_SCORE,
                    'hallucination': False,
                    'evaluation': '',
                    'llm_error': 'empty judge output',
                    'eval_details': {
                        'llm_score': 0.0,
                        'max_score': self.MAX_SCORE,
                        'hallucination': False,
                        'evaluation': '',
                        'llm_error': 'empty judge output',
                    },
                })
                continue

            clean_output = extract_non_reasoning_content(str(judge_output))
            score = 0.0
            evaluation = ''
            hallucination = False

            # 尝试整体解析 JSON
            parsed = None
            try:
                parsed = _json.loads(clean_output)
            except _json.JSONDecodeError:
                json_match = re.search(r'\{[^{}]*\}', clean_output, re.DOTALL)
                if json_match:
                    try:
                        parsed = _json.loads(json_match.group())
                    except _json.JSONDecodeError:
                        pass

            if parsed and isinstance(parsed, dict):
                # 新格式：三维度得分各 0-10，取平均值为最终分
                dim_scores = []
                for key in self._DIM_SCORE_KEYS:
                    try:
                        dim_scores.append(float(parsed[key]))
                    except (KeyError, TypeError, ValueError):
                        pass
                if dim_scores:
                    score = min(max(sum(dim_scores) / len(dim_scores), 0.0), self.MAX_SCORE)
                else:
                    # 兼容旧格式 'score' 字段
                    try:
                        score = float(parsed.get('score', 0.0))
                        score = min(max(score, 0.0), self.MAX_SCORE)
                    except (TypeError, ValueError):
                        pass
                evaluation = str(parsed.get('evaluation', ''))
                hallucination = bool(parsed.get('hallucination', False))
            else:
                # JSON 解析失败，回退到正则提取维度分之和
                dim_matches = re.findall(
                    r'(?:核心事实一致性得分|专业准确性得分|表述完整性得分)["\s]*:\s*([\d.]+)',
                    clean_output,
                )
                if dim_matches:
                    try:
                        vals = [float(x) for x in dim_matches]
                        score = min(max(sum(vals) / len(vals), 0.0), self.MAX_SCORE)
                    except ValueError:
                        pass
                else:
                    score_match = re.search(
                        r'["\']score["\']\s*:\s*["\']?([\d.]+)["\']?', clean_output, re.IGNORECASE
                    )
                    if score_match:
                        try:
                            score = float(score_match.group(1))
                            score = min(max(score, 0.0), self.MAX_SCORE)
                        except ValueError:
                            pass

            details.append({
                'prompt': prompts[i],
                'pred': pred,
                'refr': ref,
                'judge_output': judge_output,
                'llm_score': score,
                'max_score': self.MAX_SCORE,
                'hallucination': hallucination,
                'evaluation': evaluation,
                'eval_details': {
                    'llm_score': score,
                    'max_score': self.MAX_SCORE,
                    'hallucination': hallucination,
                    'evaluation': evaluation,
                    'judge_output': judge_output,
                },
            })

        return {'details': details}

    def evaluate(self, k, n, original_dataset: Dataset, **score_kwargs):
        results = super().evaluate(k, n, original_dataset, **score_kwargs)

        details = results.get('details', [])
        valid = [d for d in details if d.get('llm_score') is not None]
        if valid:
            hallucinated = sum(1 for d in valid if d.get('hallucination', False))
            results['hallucination_rate'] = round(hallucinated / len(valid) * 100, 2)
        else:
            results['hallucination_rate'] = 0.0

        return results
