from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_217: 代维-自主规划
# Metric: TelecomLLMJudgeEvaluator
# 该任务固定的系统提示词（取自源文件提示词列众数）
SYSTEM_INSTRUCTION = "你是LTE基站维护高级工程师。请根据告警信息制定完整的故障处理步骤，覆盖远程处理（重启、参数调整、配置核查）与现场处理（光模块/光纤/天馈/电源），并说明每一步的目的与风险。"

task_217_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_217_infer_cfg = dict(
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

task_217_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_217_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_217',
        path='data/custom_task/task_217.jsonl',
        reader_cfg=task_217_reader_cfg,
        infer_cfg=task_217_infer_cfg,
        eval_cfg=task_217_eval_cfg,
    )
]
