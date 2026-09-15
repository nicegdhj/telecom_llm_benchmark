from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

task_101_reader_cfg = dict(
    input_columns=["input"],
    output_column="output",
)

task_101_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=dict(
            round=[
                dict(role="HUMAN", prompt="{input}"),
                dict(role="BOT", prompt=""),
            ],
        ),
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

task_101_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

task_101_datasets = [
    dict(
        type=CustomDataset,
        abbr="task_101",
        path="data/custom_task/task_101.jsonl",
        reader_cfg=task_101_reader_cfg,
        infer_cfg=task_101_infer_cfg,
        eval_cfg=task_101_eval_cfg,
    )
]
