from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer

from ais_bench.benchmark.datasets import TeleQnADataset
from ais_bench.benchmark.openicl.icl_evaluator import AccEvaluator
from ais_bench.benchmark.utils.postprocess.text_postprocessors import first_option_postprocess

# Reader configuration
teleqna_reader_cfg = dict(
    input_columns=['question', 'A', 'B', 'C', 'D','E'],
    output_column='answer',
)

# Inference configuration
teleqna_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=f'{{question}}\nPlease select the correct answer from the options provided.</E>\nA. {{A}}\nB. {{B}}\nC. {{C}}\nD. {{D}}\nE. {{E}}\nAnswer:'
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

# Evaluation configuration
teleqna_eval_cfg = dict(
    evaluator=dict(type=AccEvaluator),
    pred_postprocessor=dict(type=first_option_postprocess,options='ABCDE'),
)

# Dataset configuration
teleqna_datasets = [
    dict(
        type=TeleQnADataset,
        abbr='teleqna',
        path='data/teleqna',
        file_name='TeleQnA.txt',
        reader_cfg=teleqna_reader_cfg,
        infer_cfg=teleqna_infer_cfg,
        eval_cfg=teleqna_eval_cfg,
    )
]
