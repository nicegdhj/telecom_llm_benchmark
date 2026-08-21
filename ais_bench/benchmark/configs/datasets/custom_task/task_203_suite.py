from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_203: 代维-知识理解
# Metric: TelecomLLMJudgeEvaluator
task_203_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_203_infer_cfg = dict(
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

task_203_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_203_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_203',
        path='data/custom_task/task_203.jsonl',
        reader_cfg=task_203_reader_cfg,
        infer_cfg=task_203_infer_cfg,
        eval_cfg=task_203_eval_cfg,
    )
]
