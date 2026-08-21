from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_201: 资源管理-知识理解
# Metric: TelecomLLMJudgeEvaluator
task_201_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_201_infer_cfg = dict(
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

task_201_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_201_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_201',
        path='data/custom_task/task_201.jsonl',
        reader_cfg=task_201_reader_cfg,
        infer_cfg=task_201_infer_cfg,
        eval_cfg=task_201_eval_cfg,
    )
]
