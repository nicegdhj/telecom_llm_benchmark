from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import TelecomLLMJudgeEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_229: 核心网-意图识别-参数提取（汇聚任务，2个子分类）
# Metric: TelecomLLMJudgeEvaluator
# 子分类: 参数提取1, 参数提取2
# 数据目录: data/custom_task/task_229/
# 汇聚准确率 = Σ(各子类正确数) / Σ(各子类总数)

task_229_sub_sets = ["参数提取1", "参数提取2"]

task_229_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_229_infer_cfg = dict(
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

task_229_eval_cfg = dict(
    evaluator=dict(type=TelecomLLMJudgeEvaluator),
)

# 导出数据集配置（多子数据集列表，ais_bench 分别推理+评测，eval_judge 自动汇聚）
task_229_datasets = []
for _name in task_229_sub_sets:
    task_229_datasets.append(
        dict(
            type=CustomDataset,
            abbr=f'task_229_{_name}',
            path=f'data/custom_task/task_229/{_name}.jsonl',
            reader_cfg=task_229_reader_cfg,
            infer_cfg=task_229_infer_cfg,
            eval_cfg=task_229_eval_cfg,
        )
    )

del _name
