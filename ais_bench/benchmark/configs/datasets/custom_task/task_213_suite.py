from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_213: 集客-知识理解
# Metric: TelecomLLMJudgeEvaluator
task_213_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_213_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=dict(
            round=[
                dict(role='HUMAN', prompt='{input}'),
                dict(role='BOT', prompt=''),
            ],
        ),
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

task_213_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_213_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_213',
        path='data/custom_task/task_213.jsonl',
        reader_cfg=task_213_reader_cfg,
        infer_cfg=task_213_infer_cfg,
        eval_cfg=task_213_eval_cfg,
    )
]
