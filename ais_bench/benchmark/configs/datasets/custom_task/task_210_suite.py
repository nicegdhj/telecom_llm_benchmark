from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import JsonFieldEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_210: 核心网-意图识别-分类（汇聚任务，2个子分类）
# Metric: JsonFieldEvaluator
# 子分类: 分类1, 分类2
# 数据目录: data/custom_task/task_210/
# 汇聚准确率 = Σ(各子类正确数) / Σ(各子类总数)

task_210_sub_sets = ["分类1", "分类2"]

task_210_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_210_infer_cfg = dict(
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

task_210_eval_cfg = dict(
    evaluator=dict(
        type=JsonFieldEvaluator,
        field_config={'分类结果': {'match_type': 'exact', 'weight': 1.0},
 '分类标号': {'match_type': 'exact', 'weight': 1.0}},
        default_match_type='exact',
        return_details=True,
        strict_mode=True,
    ),
)

# 导出数据集配置（多子数据集列表，ais_bench 分别推理+评测，eval_judge 自动汇聚）
task_210_datasets = []
for _name in task_210_sub_sets:
    task_210_datasets.append(
        dict(
            type=CustomDataset,
            abbr=f'task_210_{_name}',
            path=f'data/custom_task/task_210/{_name}.jsonl',
            reader_cfg=task_210_reader_cfg,
            infer_cfg=task_210_infer_cfg,
            eval_cfg=task_210_eval_cfg,
        )
    )

del _name
