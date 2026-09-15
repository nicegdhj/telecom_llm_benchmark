from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_219: 网络投诉-自主规划
# Metric: TelecomLLMJudgeEvaluator
# 该任务固定的系统提示词（取自源文件提示词列众数）
SYSTEM_INSTRUCTION = "请根据给定的投诉现象，进行故障原因分析并给出详细的处理建议。"

task_219_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_219_infer_cfg = dict(
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

task_219_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_219_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_219',
        path='data/custom_task/task_219.jsonl',
        reader_cfg=task_219_reader_cfg,
        infer_cfg=task_219_infer_cfg,
        eval_cfg=task_219_eval_cfg,
    )
]
