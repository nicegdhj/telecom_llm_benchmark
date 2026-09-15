import copy
import os
import re
from typing import List
from collections import defaultdict

from datasets import Dataset

from ais_bench.benchmark.registry import ICL_EVALUATORS
from ais_bench.benchmark.openicl.icl_evaluator.icl_base_evaluator import BaseEvaluator
from ais_bench.benchmark.utils.config.build import build_model_from_cfg
from ais_bench.benchmark.utils.logging.logger import AISLogger
from ais_bench.benchmark.utils.postprocess.model_postprocessors import extract_non_reasoning_content

DEFAULT_PROMPT_TEMPLATE = """You are an objective and intelligent evaluator. Your task is to score the student's answer against the correct reference answer. 
The maximum score you can give is {max_score}.

Evaluation Criteria:
1. Math & Engineering Equivalence: If the answer involves formulas or equations, focus on mathematical equivalence. Ignore different algebraic arrangements (e.g., `t^2/2` vs `1/2 t^2`), extraneous assignments (e.g., `y(t) = `), and purely typographical or LaTeX syntax differences (e.g., `\frac` vs `\dfrac`, missing brackets, spaces).
2. Semantic Text Equivalence: If the answer is natural language, evaluate based on core meaning and semantic similarity rather than exact string matching. Do not penalize for synonyms, paraphrasing, or varying levels of detail as long as the core concept is correct (e.g., "山" and "山川" should be considered semantically equivalent if they refer to the same core entity).
3. Minor Errors: Ignore differences in punctuation, capitalization, and minor typos that do not alter the fundamental meaning or correctness.
4. Partial Credit: If the student's answer is partially correct or captures only part of a complex reference answer, award a proportional score based on {max_score}. If the answer is fundamentally wrong or contradictory, score 0.

Correct Answer:
{reference}

Student's Answer:
{prediction}

Please output the score only as a number at the end of your response."""


@ICL_EVALUATORS.register_module()
class LLMJudgeEvaluator(BaseEvaluator):
    def __init__(self, model_cfg: dict = None, prompt_template: str = None, **kwargs) -> None:
        super().__init__()
        self.prompt_template = prompt_template or DEFAULT_PROMPT_TEMPLATE
        self.logger = AISLogger()
        env_model_cfg = self._build_eval_model_cfg_from_env()
        if env_model_cfg:
            # 显式传入了配置，直接使用
            self.model_cfg = env_model_cfg
        else:
            # 未传入配置，尝试从 SCORE_* 环境变量自动构建打分模型配置
            self.model_cfg = None

        if not self.model_cfg:
            self.logger.info(
                "LLMJudgeEvaluator: model_cfg is None 且未检测到 SCORE_* 环境变量，"
                "评估器将无法调用 LLM 评分。"
            )
            self.model = None
        else:
            self.model = build_model_from_cfg(self.model_cfg)

    @staticmethod
    def _build_eval_model_cfg_from_env() -> dict:
        """从 SCORE_* 环境变量构建打分模型配置（与推理的 LOCAL_* 变量完全解耦）。

        自动分支：
          - 检测到 SCORE_API_KEY（非空）→ API 模式
              必填：SCORE_MODEL_NAME, SCORE_API_KEY, SCORE_URL
          - 未检测到 SCORE_API_KEY         → 本地服务模式
              必填：SCORE_MODEL_NAME, SCORE_HOST_IP, SCORE_HOST_PORT
              可选：SCORE_URL（默认自动拼接 /v1/chat/completions）

        公共可选变量：
          SCORE_LLM_CONCURRENCY（并发数，默认 5），EVAL_VERBOSE（日志，默认 false）
          SCORE_MODEL_TYPE（模型类型，默认 maas；设为 vllm 则使用 VLLMCustomAPIChat）

        Returns:
            完整的 model_cfg dict，若必填变量缺失则返回 None。
        """
        from ais_bench.benchmark.models import VLLMCustomAPIChat
        from ais_bench.benchmark.utils.postprocess.model_postprocessors import (
            extract_non_reasoning_content,
        )
        model_type  = os.environ.get("SCORE_MODEL_TYPE", "maas").lower()
        if "bailian" in model_type:
            from ais_bench.benchmark.models.api_models.bailian_api import BailianAPI as EVAL_API_CLASS
        else:
            from ais_bench.benchmark.models.api_models.maas_api import MaaSAPI as EVAL_API_CLASS
        model_name = os.environ.get("SCORE_MODEL_NAME")
        api_key = os.environ.get("SCORE_API_KEY", "").strip()
        concurrency = int(os.environ.get("SCORE_LLM_CONCURRENCY", "5"))
        verbose = os.environ.get("EVAL_VERBOSE", "false").lower() == "true"

        # 公共基础字段
        base_cfg = dict(
            type=EVAL_API_CLASS,
            attr="service",
            abbr="eval_model",
            path="",
            model=model_name,
            stream=False,
            request_rate=0,
            retry=1,
            max_out_len=4096,
            batch_size=concurrency,
            trust_remote_code=False,
            verbose=verbose,
            generation_kwargs=dict(
                temperature=0.01,
                ignore_eos=False,
                enable_thinking=False,
            ),
            pred_postprocessor=dict(type=extract_non_reasoning_content),
        )

        if api_key:
            # ── 分支 A：API 模式（有 api_key，走云端服务）────────
            AISLogger().info('================Bailian打分模型=======================')
            score_url = os.environ.get("SCORE_URL", "")
            if not all([model_name, score_url]):
                return None
            return {
                **base_cfg,
                "api_key": api_key,
                "url": score_url,
                # MaaS 模式下 host_ip / host_port 从 url 中隐含，给占位值避免校验报错
                "host_ip": os.environ.get("SCORE_HOST_IP", "localhost"),
                "host_port": int(os.environ.get("SCORE_HOST_PORT", "443")),
            }
        else:

            AISLogger().info('================使用本地打分模型 MaaStype=======================')
            # ── 分支 B：本地服务模式（无 api_key，走内网自托管服务）──────────
            host_ip = os.environ.get("SCORE_HOST_IP")
            host_port = os.environ.get("SCORE_HOST_PORT")
            if not all([model_name, host_ip, host_port]):
                return None
            try:
                host_port_int = int(host_port)
            except ValueError:
                return None
            score_url = os.environ.get(
                "SCORE_URL",
                f"http://{host_ip}:{host_port}/v1/chat/completions",
            )
            return {
                **base_cfg,
                "host_ip": host_ip,
                "host_port": host_port_int,
                "url": score_url,
            }

    def evaluate(self, k, n, original_dataset: Dataset, **score_kwargs):
        if 'predictions' in score_kwargs and 'references' in score_kwargs:
            if len(score_kwargs['predictions']) != len(score_kwargs['references']):
                return {'error': 'Predictions and references must have the same length'}

        score_kwargs['predictions'] = self.pred_postprocess(score_kwargs.get('predictions', []))
        # Enforce `test_set` in `score_kwargs` is `original_dataset`
        score_kwargs['test_set'] = original_dataset
        results = self.score(**score_kwargs)
        if 'error' in results:
            return results

        details = results.get('details', [])

        total_score = 0.0
        total_max_score = 0.0
        subdivision_scores = defaultdict(float)
        subdivision_max_scores = defaultdict(float)
        # self.logger.info(details)
        for i, detail in enumerate(details):
            if i < len(original_dataset):
                example = original_dataset[i]
                subdiv = example.get('subdivision', 'unknown')
                idx = example.get('idx', i)
                detail['example_abbr'] = f"{subdiv}_{idx}"
            else:
                subdiv = 'unknown'

            score = detail.get('llm_score')  # None 表示大模型调用失败，不计入统计
            max_score = detail.get('max_score', 1.0)

            if score is None:
                # 大模型调用失败，跳过本条，不累加分数和最大分
                continue

            total_score += score
            total_max_score += max_score
            subdivision_scores[subdiv] += score
            subdivision_max_scores[subdiv] += max_score

        # eval_results = {
        #     'llm_judge_score_sum': round(total_score, 2),
        #     'llm_judge_max_score_sum': round(total_max_score, 2),
        # }
        eval_results = {}
        for subdiv in subdivision_scores:
            score = subdivision_scores[subdiv]
            max_score = subdivision_max_scores[subdiv]
            if max_score == 0:
                percentage = 0.0
            else:
                percentage = (score / max_score) * 100
            eval_results[f'{subdiv}/llm_judge_percentage'] = round(percentage, 2)

        eval_results['details'] = details
        return eval_results

    def score(self, predictions: List, references: List, test_set: Dataset = None) -> dict:
        if not self.model:
            return {'error': 'Model instance could not be created for LLMJudgeEvaluator.'}

        prompts = []
        max_scores = []
        for i, (pred, ref) in enumerate(zip(predictions, references)):
            max_score = 1.0
            if test_set and 'score' in test_set.features:
                score_val = test_set[i].get('score')
                if score_val is not None:
                    match = re.search(r'([\d.]+)', str(score_val))
                    if match:
                        max_score = float(match.group(1))

            max_scores.append(max_score)
            prompt = self.prompt_template.format(max_score=max_score, reference=ref, prediction=pred)
            prompts.append(prompt)

        self.logger.info(
            f"[LLMJudge] 打分模型: type={type(self.model).__name__}, "
            f"url={getattr(self.model, 'url', 'N/A')}, "
            f"model={getattr(self.model, 'model', 'N/A')}, "
            f"共 {len(prompts)} 条待评分"
        )

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
                            max_out_len=getattr(self.model, 'max_out_len', 128),
                            output=output,
                            session=session
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
            judgements = self.model.generate(prompts, max_out_len=getattr(self.model, 'max_out_len', 128))
        details = []
        for i, (pred, ref, judge_output, max_score) in enumerate(zip(predictions, references, judgements, max_scores)):
            score = 0.0
            if judge_output is None or str(judge_output).strip() == "":
                self.logger.warning(f"Empty or missing judge output at index {i}, score set to 0. "
                                    f"Prompt: {prompts[i][:100]}...")

                #  self.logger.error(ICLE_CODES.UNKNOWN_ERROR, f"Empty or
                #  missing judge output at index {i}, score set to 0. "f"Prompt{prompts[i][:100]}...")

                details.append({
                    'prompt': prompts[i],
                    'pred': pred,
                    'refr': ref,
                    'judge_output': "",
                    'llm_score': None,  # 大模型调用失败，得分设为空，不计入最终统计
                    'llm_error': 'empty judge output',
                    'eval_details': {
                        'llm_score': 0.0,
                        'max_score': max_score,
                        'judge_output': "",
                        'llm_error': 'empty judge output',
                    },
                })
                continue

            # 1. 过滤掉大模型思考过程的 <think>...</think>，以免提取到里面的时间或举例数字
            clean_output = str(judge_output)
            clean_output = extract_non_reasoning_content(clean_output)

            # 2. 优先通过正则表达式尝试提取 "score": 数字
            score_match = re.search(r'["\']score["\']\s*:\s*["\']?([\d.]+)["\']?', clean_output, flags=re.IGNORECASE)

            if score_match:
                extracted_str = score_match.group(1)
                self.logger.info(f"Extracted score from JSON field: {extracted_str}")
                try:
                    score = float(extracted_str)
                    score = min(max(score, 0.0), max_score)
                except ValueError:
                    pass
            else:
                # 3. 实在没有则回退：先尝试找独占一行的纯分数
                # self.logger.info(clean_output)
                line_match = re.search(r'^\s*([\d.]+)\s*$', clean_output, flags=re.MULTILINE)
                if line_match:
                    extracted_str = line_match.group(1)
                    self.logger.info(f"No score field, but found a standalone number on a line: {extracted_str}")
                    try:
                        score = float(extracted_str)
                        score = min(max(score, 0.0), max_score)
                    except ValueError:
                        pass
                else:
                    # 4. 如果连独占一行的数字都没有，退回到找整个文本的最后一个数字
                    matches = re.findall(r'([\d.]+)', clean_output)
                    self.logger.info(f"No score field found, fallback to digits (taking the last one): {matches}")
                    if matches:
                        try:
                            score = float(matches[-1])
                            score = min(max(score, 0.0), max_score)
                        except ValueError:
                            pass

            details.append({
                'prompt': prompts[i],
                'pred': pred,
                'refr': ref,
                'judge_output': judge_output,
                'llm_score': score,
                'max_score': max_score,
                'eval_details': {
                    'llm_score': score,
                    'max_score': max_score,
                    'judge_output': judge_output,
                },
            })

        return {'details': details}
