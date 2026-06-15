import os
import re
import json
from typing import List

from datasets import Dataset

from ais_bench.benchmark.registry import ICL_EVALUATORS
from ais_bench.benchmark.openicl.icl_evaluator.llm_judge_evaluator import LLMJudgeEvaluator
from ais_bench.benchmark.utils.postprocess.model_postprocessors import extract_non_reasoning_content
from ais_bench.benchmark.utils.logging.logger import AISLogger

@ICL_EVALUATORS.register_module()
class AlarmJudgeEvaluator(LLMJudgeEvaluator):
    def __init__(self, model_cfg: dict = None, prompt_template: str = None, **kwargs) -> None:
        super().__init__(model_cfg=model_cfg, prompt_template=prompt_template, **kwargs)
        self.logger = AISLogger()
    def preprocess_reference(self, ref: str) -> str:
        # Extract section 一 and 三 from the reference
        section_1_match = re.search(r'(##\s*✅\s*一、.*?)(?=##\s*✅\s*[一二三四五]、|$)', ref, flags=re.DOTALL)
        section_3_match = re.search(r'(##\s*✅\s*三、.*?)(?=##\s*✅\s*[一二三四五]、|$)', ref, flags=re.DOTALL)
        
        parts = []
        if section_1_match:
            parts.append(section_1_match.group(1).strip())
        if section_3_match:
            parts.append(section_3_match.group(1).strip())
        self.logger.info("----------------------------------------------------------------------------------")     
        self.logger.info(f"[AlarmJudge] Reference: {parts}")    
        if not parts:
            return ref
        return "\n\n".join(parts)

    def score(self, predictions: List, references: List, test_set: Dataset = None) -> dict:
        if not self.model:
            return {'error': 'Model instance could not be created for AlarmJudgeEvaluator.'}

        prompts = []
        max_scores = []
        for i, (pred, ref) in enumerate(zip(predictions, references)):
            max_score = 30.0
            
            if test_set and 'score' in test_set.features:
                score_val = test_set[i].get('score')
                if score_val is not None:
                    match = re.search(r'([\d.]+)', str(score_val))
                    if match:
                        max_score = float(match.group(1))

            processed_ref = self.preprocess_reference(ref)
            
            full_question = test_set[i].get('question', '') if test_set else ''
            input_match = re.search(r'(【输入数据】.*?)(?=【任务要求】|$)', full_question, flags=re.DOTALL)
            original_prompt = input_match.group(1).strip() if input_match else full_question
            
            max_scores.append(max_score)
            self.logger.info(f"original_prompt: {original_prompt}")
            prompt = self.prompt_template.replace("{max_score}", str(max_score)).replace("{reference}", processed_ref).replace("{prediction}", pred).replace("{original_prompt}", original_prompt)
            prompts.append(prompt)

        self.logger.info(
            f"[AlarmJudge] 打分模型: type={type(self.model).__name__}, "
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
                            max_out_len=getattr(self.model, 'max_out_len', 1024),
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
            judgements = self.model.generate(prompts, max_out_len=getattr(self.model, 'max_out_len', 1024))

        details = []
        for i, (pred, ref, judge_output, max_score) in enumerate(zip(predictions, references, judgements, max_scores)):
            score = 0.0
            parsed_json = {}
            if judge_output is None or str(judge_output).strip() == "":
                self.logger.warning(f"Empty or missing judge output at index {i}, score set to 0. ")
                details.append({
                    'prompt': prompts[i],
                    'pred': pred,
                    'refr': ref,
                    'judge_output': "",
                    'llm_score': None,
                    'llm_error': 'empty judge output',
                })
                continue

            clean_output = str(judge_output)
            clean_output = extract_non_reasoning_content(clean_output)

            json_match = re.search(r'\{.*\}', clean_output, flags=re.DOTALL)
            if json_match:
                json_str = json_match.group(0)
                try:
                    parsed_json = json.loads(json_str)
                    scores = parsed_json.get('scores', {})
                    if isinstance(scores, dict):
                        clustering = float(scores.get('clustering', 0))
                        root_cause = float(scores.get('root_cause', 0))
                        hallucination = float(scores.get('hallucination_check', 0))
                        score = clustering + root_cause + hallucination
                    else:
                        score = 0.0
                except Exception as e:
                    self.logger.warning(f"Failed to parse JSON for index {i}: {e}. Fallback to regex.")
                    def extract_score(key):
                        match = re.search(rf'"{key}"\s*:\s*([\d.]+)', json_str)
                        return float(match.group(1)) if match else 0.0

                    clustering = extract_score("clustering")
                    root_cause = extract_score("root_cause")
                    hallucination = extract_score("hallucination_check")
                    score = clustering + root_cause + hallucination

            details.append({
                'prompt': prompts[i],
                'pred': pred,
                'refr': ref,
                'judge_output': judge_output,
                'parsed_json': parsed_json,
                'llm_score': score,
                'max_score': max_score
            })

        return {'details': details}
