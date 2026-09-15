from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_204: 个人业务-知识理解
# Metric: TelecomLLMJudgeEvaluator
task_204_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_204_infer_cfg = dict(
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

task_204_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_204_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_204',
        path='data/custom_task/task_204.jsonl',
        reader_cfg=task_204_reader_cfg,
        infer_cfg=task_204_infer_cfg,
        eval_cfg=task_204_eval_cfg,
    )
]
