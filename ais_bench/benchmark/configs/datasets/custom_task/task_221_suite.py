from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_221: 个人业务-诊断分析
# Metric: TelecomLLMJudgeEvaluator
# 该任务固定的系统提示词（取自源文件提示词列众数）
SYSTEM_INSTRUCTION = "你是业务平台工作台故障诊断专家。按\"先远程可查证、后现场排查\"的优先级，结合工作台的拓扑可视化、多维数据关联分析、巡检、健康度评分等能力逐步定位，输出推理过程和最终结论。"

task_221_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_221_infer_cfg = dict(
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

task_221_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置
task_221_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_221',
        path='data/custom_task/task_221.jsonl',
        reader_cfg=task_221_reader_cfg,
        infer_cfg=task_221_infer_cfg,
        eval_cfg=task_221_eval_cfg,
    )
]
