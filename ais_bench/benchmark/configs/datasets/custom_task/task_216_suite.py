from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_216: 个人业务-自主规划
# Metric: TelecomLLMJudgeEvaluator
# 该任务固定的系统提示词（取自源文件提示词列众数）
SYSTEM_INSTRUCTION = "你是业务平台工作台运维规划智能体。根据输入的平台与场景输出可执行方案，包含goal、assumptions、steps、tools_or_sources、verification、rollback。涉及割接、局数据、参数修改、重启、切换时必须包含审批、备份与回退点。"

task_216_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_216_infer_cfg = dict(
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

task_216_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_216_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_216',
        path='data/custom_task/task_216.jsonl',
        reader_cfg=task_216_reader_cfg,
        infer_cfg=task_216_infer_cfg,
        eval_cfg=task_216_eval_cfg,
    )
]
