from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import AccEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_211: 监控排障-意图识别
# Metric: AccEvaluator
task_211_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_211_infer_cfg = dict(
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

task_211_eval_cfg = dict(
    evaluator=dict(type=AccEvaluator),
)

# 导出数据集配置
task_211_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_211',
        path='data/custom_task/task_211.jsonl',
        reader_cfg=task_211_reader_cfg,
        infer_cfg=task_211_infer_cfg,
        eval_cfg=task_211_eval_cfg,
    )
]
