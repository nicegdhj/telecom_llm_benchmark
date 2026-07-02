import json
import os.path as osp
import re
from os import environ
import random

from datasets import Dataset

from ais_bench.benchmark.openicl.icl_evaluator import BaseEvaluator
from ais_bench.benchmark.registry import (ICL_EVALUATORS, LOAD_DATASET,
                                  TEXT_POSTPROCESSORS)
from ais_bench.benchmark.datasets.utils.datasets import get_data_path
from ais_bench.benchmark.utils.logging.logger import AISLogger

from .base import BaseDataset
logger = AISLogger()

@LOAD_DATASET.register_module()
class BBHDataset(BaseDataset):

    @staticmethod
    def load(path: str, name: str):
        path = get_data_path(path)
        if environ.get('DATASET_SOURCE') == 'ModelScope':
            from modelscope import MsDataset
            dataset = MsDataset.load(path, subset_name=name, split='test')
        else:
            with open(osp.join(path, f'{name}.json'), 'r') as f:
                data = json.load(f)['examples']
            dataset = Dataset.from_list(data)
# --- 新增：随机抽取 2/13 的数据 ---
        num_samples = len(dataset)
        if num_samples > 0:
            # 计算需要抽取的样本数量
            target_size = max(1, (num_samples * 2) // 13)
            
            # 生成固定种子的随机索引
            indices = list(range(num_samples))
            random.seed(42)  # 固定种子保证结果可复现
            random.shuffle(indices)
            
            # 选取前 2/13 的索引并重新构建数据集
            selected_indices = indices[:target_size]
            dataset = dataset.select(selected_indices).flatten_indices()
            
            logger.info(f"BBH '{name}' sampled: {num_samples} -> {len(dataset)} (2/13)")
        # -------------------------------
        return dataset


@TEXT_POSTPROCESSORS.register_module('bbh-mcq')
def bbh_mcq_postprocess(text: str) -> str:
    ans = text
    ans_line = ans.split('answer is ')
    if len(ans_line) != 1:
        ans = ans_line[1].strip()
    match = re.search(r'\(([A-Z])\)*', ans)
    if match:
        return match.group(1)
    match = re.search(r'([A-Z])', ans)
    if match:
        return match.group(1)
    return ans


@TEXT_POSTPROCESSORS.register_module('bbh-freeform')
def bbh_freeform_postprocess(text: str) -> str:
    def clean_debris(s: str) -> str:
        # 去除开头的冒号、星号、空白符
        s = re.sub(r'^[:：\*\s]+', '', s)
        # 去除结尾的句号、星号、空白符
        s = re.sub(r'[\.\*\s]+$', '', s)
        return s
    ans = text
    keyword = 'answer is'
    if keyword in ans:
        idx = ans.rfind(keyword)
        prefix = ans[:idx]
        suffix = ans[idx + len(keyword):]
        star_count = prefix.count('**')
        if star_count % 2 != 0:
            # 如果是奇数，说明分割点在加粗内部，给后面补上星号
            ans = '**' + suffix
        else:
            ans = suffix        

    # 1. 处理类似 "**Answer:** invalid", "**Answer**: invalid", "**答案:** invalid" 等情况
    # 提前把它的前缀过滤掉，并将剩余的部分保留下来。加入 re.DOTALL 以便处理 **Answer:** 和 invalid 之间有换行符的情况
    match_prefix = re.search(
    r'[\#\*\s]*(?:final\s+)?(?:answer|答案)[\#\*\s]*[:：]?[\#\*\s]*([\s\S]*?)(?:\*\*|###|$)', 
    ans, 
    flags=re.IGNORECASE | re.DOTALL
    )
    if match_prefix:
        temp_ans = match_prefix.group(1).strip()
        if temp_ans:
            # 给 ans 重新赋值，继续往下走，这样也能正确处理 **Answer:** **invalid** 的情况
            ans = temp_ans

    # 2. 传统逻辑：提取被单独包裹在 **XXX** 内的内容
    match = re.search(r'\*\*(.*?)\*\*', ans,flags=re.DOTALL)
    if match:
        extracted = match.group(1).strip()
        
        # 防止漏网之鱼：如果被单独提取出来的刚好是无意义的标题 "Answer:"
        if extracted.lower().startswith('answer:'):
            return clean_debris(extracted[7:])
        elif extracted.lower().startswith('answer'):
            clean_extracted = re.sub(r'^(?i)answer\s*', '', extracted)
            return clean_debris(clean_extracted[7:])
        match_letter = re.match(r'^[a-eA-E][:：]\s*(.*)', extracted)
        if match_letter:
            return clean_debris(match_letter.group(1))
        return clean_debris(extracted)
    lines_fallback = [line.strip() for line in ans.split('\n') if line.strip()]
    if lines_fallback:
        return clean_debris(lines_fallback[-1])
    return clean_debris(ans)


@ICL_EVALUATORS.register_module()
class BBHEvaluator(BaseEvaluator):

    def score(self, predictions, references):
        if len(predictions) != len(references):
            return {
                'error': 'predictions and references have different '
                'length'
            }

        predictions = [bbh_freeform_postprocess(pred) for pred in predictions]

        details = []
        cnt = 0
        for pred, ref in zip(predictions, references):
            detail = {'pred': pred, 'answer': ref, 'correct': False}
            if pred == ref:
                cnt += 1
                detail['correct'] = True
            details.append(detail)

        score = cnt / len(predictions) * 100

        return {'score': score, 'details': details}


@ICL_EVALUATORS.register_module()
class BBHEvaluator_mcq(BaseEvaluator):

    def score(self, predictions, references):
        if len(predictions) != len(references):
            return {
                'error': 'predictions and references have different '
                'length'
            }
        details = []
        cnt = 0
        for pred, ref in zip(predictions, references):
            detail = {'pred': pred, 'answer': ref, 'correct': False}
            if pred == ref:
                cnt += 1
                detail['correct'] = True
            details.append(detail)

        score = cnt / len(predictions) * 100

        return {'score': score, 'details': details}
