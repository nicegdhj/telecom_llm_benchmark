from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.datasets import AlarmDataDataset
from ais_bench.benchmark.openicl.icl_evaluator import AlarmClusterEvaluator

alarm_data_reader_cfg = dict(
    input_columns=["question"],
    output_column="answer",
)

alarm_data_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=f"{{question}}",
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

alarm_data_eval_cfg = dict(
    evaluator=dict(
        type=AlarmClusterEvaluator,
    ),
)

alarm_data_datasets = [
    dict(
        abbr="alarm_data",
        type=AlarmDataDataset,
        path="data/alarm_data/train_data_v3_overfit.json",
        name="alarm_data",
        reader_cfg=alarm_data_reader_cfg,
        infer_cfg=alarm_data_infer_cfg,
        eval_cfg=alarm_data_eval_cfg,
    )
]
