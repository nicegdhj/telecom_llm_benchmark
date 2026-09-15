from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_240: 家客-意图识别-分类（汇聚任务，7个子分类）
# Metric: TelecomLLMJudgeEvaluator
# 子分类: 分类1, 分类2, 分类3, 分类4, 分类5, 分类6, 分类7
# 数据目录: data/custom_task/task_240/
# 汇聚准确率 = Σ(各子类正确数) / Σ(各子类总数)

task_240_sub_sets = ["分类1", "分类2", "分类3", "分类4", "分类5", "分类6", "分类7"]

task_240_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_240_infer_cfg = dict(
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

task_240_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置（多子数据集列表，ais_bench 分别推理+评测，eval_judge 自动汇聚）
task_240_datasets = []
for _name in task_240_sub_sets:
    task_240_datasets.append(
        dict(
            type=CustomDataset,
            abbr=f'task_240_{_name}',
            path=f'data/custom_task/task_240/{_name}.jsonl',
            reader_cfg=task_240_reader_cfg,
            infer_cfg=task_240_infer_cfg,
            eval_cfg=task_240_eval_cfg,
        )
    )

del _name
