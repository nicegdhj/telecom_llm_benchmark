import os

from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# 数据目录下的 JSONL 文件列表（文件名不含扩展名）
task_102_files = [
    "传输-变更监控-故障处置智能体-知识型",
    "传输-故障处理-故障处置智能体-知识型",
    "核心网-投诉处理-信令分析-知识型",
    "集客-投诉处理-智能排障-知识型",
    "集客-业务开通-数据自服务-知识型",
    "集客-知识问答-智能问答-知识型",
    "家客-投诉处理-家宽排障智能体-知识型",
    "家客-投诉处理-装维作业智能体-知识型",
]

task_102_reader_cfg = dict(
    input_columns=["instruction"],
    output_column="output",
)

task_102_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=dict(
            round=[
                dict(role="HUMAN", prompt="{instruction}"),
                dict(role="BOT", prompt=""),
            ],
        ),
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

task_102_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

task_102_datasets = []

for _name in task_102_files:
    task_102_datasets.append(
        dict(
            type=CustomDataset,
            abbr=_name,
            path="data/task_102",
            file_name=f"{_name}.jsonl",
            reader_cfg=task_102_reader_cfg,
            infer_cfg=task_102_infer_cfg,
            eval_cfg=task_102_eval_cfg,
        )
    )

del _name
