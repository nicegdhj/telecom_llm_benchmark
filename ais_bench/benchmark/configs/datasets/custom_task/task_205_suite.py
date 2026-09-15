from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_205: 核心网-知识理解
# Metric: TelecomLLMJudgeEvaluator
task_205_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_205_infer_cfg = dict(
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

task_205_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_205_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_205',
        path='data/custom_task/task_205.jsonl',
        reader_cfg=task_205_reader_cfg,
        infer_cfg=task_205_infer_cfg,
        eval_cfg=task_205_eval_cfg,
    )
]
