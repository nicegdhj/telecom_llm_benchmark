from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_234: 入口智能体-测试集
# Metric: TelecomLLMJudgeEvaluator
task_234_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_234_infer_cfg = dict(
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

task_234_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_234_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_234',
        path='data/custom_task/task_234.jsonl',
        reader_cfg=task_234_reader_cfg,
        infer_cfg=task_234_infer_cfg,
        eval_cfg=task_234_eval_cfg,
    )
]
