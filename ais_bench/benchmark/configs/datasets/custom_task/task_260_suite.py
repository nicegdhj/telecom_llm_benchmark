from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_260: 集客-诊断分析（汇聚任务，3个子分类）
# Metric: TelecomLLMJudgeEvaluator
# 子分类: 任务1, 任务2, 任务3
# 数据目录: data/custom_task/task_260/
# 汇聚准确率 = Σ(各子类正确数) / Σ(各子类总数)

task_260_sub_sets = ["任务1", "任务2", "任务3"]

task_260_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_260_infer_cfg = dict(
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

task_260_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置（多子数据集列表，ais_bench 分别推理+评测，eval_judge 自动汇聚）
task_260_datasets = []
for _name in task_260_sub_sets:
    task_260_datasets.append(
        dict(
            type=CustomDataset,
            abbr=f'task_260_{_name}',
            path=f'data/custom_task/task_260/{_name}.jsonl',
            reader_cfg=task_260_reader_cfg,
            infer_cfg=task_260_infer_cfg,
            eval_cfg=task_260_eval_cfg,
        )
    )

del _name
