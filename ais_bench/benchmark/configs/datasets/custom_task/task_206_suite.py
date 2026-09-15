from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_206: 基础保障-知识理解
# Metric: TelecomLLMJudgeEvaluator
# 该任务固定的系统提示词（取自源文件提示词列众数）
SYSTEM_INSTRUCTION = "任务：请根据以下题目内容，从给定的选项（A/B/C/D）中选择最符合的一项。\n要求：\n1. 分析题目考查的知识点\n2. 逐一验证各选项的正确性\n3. 返回正确选项的字母及选项内容。"

task_206_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_206_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=dict(
            begin=[
                dict(role='SYSTEM', fallback_role='HUMAN', prompt=SYSTEM_INSTRUCTION),
            ],
            round=[
                dict(role='HUMAN', prompt='{input}'),
                dict(role='BOT', prompt=''),
            ],
        ),
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

task_206_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_206_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_206',
        path='data/custom_task/task_206.jsonl',
        reader_cfg=task_206_reader_cfg,
        infer_cfg=task_206_infer_cfg,
        eval_cfg=task_206_eval_cfg,
    )
]
