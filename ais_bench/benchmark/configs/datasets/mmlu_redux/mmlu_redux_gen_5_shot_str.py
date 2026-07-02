# configs/datasets/mmlu_redux/mmlu_redux.py

from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import FixKRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import AccEvaluator
from ais_bench.benchmark.datasets import MMLUReduxDataset
from ais_bench.benchmark.utils.postprocess.text_postprocessors import first_capital_postprocess, first_capital_postprocess_multi,first_option_postprocess

# 学科列表
mmlu_redux_all_sets = [
    "anatomy",
    "astronomy",
    "business_ethics",
    "clinical_knowledge",
    "college_chemistry",
    "college_computer_science",
    "college_mathematics",
    "college_medicine",
    "college_physics",
    "conceptual_physics",
    "econometrics",
    "electrical_engineering",
    "formal_logic",
    "global_facts",
    "high_school_chemistry",
    "high_school_geography",
    "high_school_macroeconomics",
    "high_school_mathematics",    
    "high_school_physics",
    "high_school_statistics",
    "high_school_us_history",
    "human_aging",
    "logical_fallacies",
    "machine_learning",
    "miscellaneous",
    "philosophy",
    "professional_accounting",
    "professional_law",
    "public_relations",
    "virology"
]

mmlu_redux_datasets = []

for _name in mmlu_redux_all_sets:
    _hint = f'The following are multiple choice questions (with answers) about {_name.replace("_", " ")}.\n\n'
    _hint += 'The examples above are already answered. Only answer the very last question.\n\n'
    
    mmlu_redux_reader_cfg = dict(
        input_columns=['input', 'A', 'B', 'C', 'D'],
        output_column='target',  
        test_split='test',
    )

    mmlu_redux_infer_cfg = dict(
        ice_template=dict(
            type=PromptTemplate,
            template='{input}\nA. {A}\nB. {B}\nC. {C}\nD. {D}\nAnswer: {target}\n',
        ),
        prompt_template=dict(
            type=PromptTemplate,
            template=f'{_hint}</E>{{input}}\nA. {{A}}\nB. {{B}}\nC. {{C}}\nD. {{D}}\nAnswer:',
            ice_token='</E>',
        ),
        retriever=dict(type=FixKRetriever, fix_id_list=[0, 1, 2, 3, 4]),
        inferencer=dict(type=GenInferencer),
    )

    mmlu_redux_eval_cfg = dict(
        evaluator=dict(type=AccEvaluator),
        pred_postprocessor=dict(type=first_option_postprocess,options='ABCDE'),  # 提取如 "C" from "The answer is C."
    )

    mmlu_redux_datasets.append(
        dict(
            abbr=f'mmlu_redux_{_name}',
            type=MMLUReduxDataset,
            path='data/mmlu_redux',  # 路径下有 anatomy/、astronomy/ 等子目录
            name=_name,
            reader_cfg=mmlu_redux_reader_cfg,
            infer_cfg=mmlu_redux_infer_cfg,
            eval_cfg=mmlu_redux_eval_cfg,
        ))

del _name, _hint