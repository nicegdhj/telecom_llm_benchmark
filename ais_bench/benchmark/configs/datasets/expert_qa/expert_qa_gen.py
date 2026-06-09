# Try importing the newly created dataset explicitly so it registers with mmengine registry
# If this script is run from the root, ais_bench is in the python path
from ais_bench.benchmark.datasets.expert_qa import ExpertQADataset
from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import JiebaRougeEvaluator
import os
expert_qa_datasets = []

base_data_path = 'data/Expert_QA_Corpus'
# If path is relative to the execution root (which it usually is for AISBench)
abs_base_data_path = os.path.abspath(base_data_path)

if os.path.exists(abs_base_data_path):
    for root, dirs, files in os.walk(abs_base_data_path):
        for file in files:
            if (file.endswith('.xlsx') or file.endswith('.jsonl')) and not file.startswith('~'):
                # Get relative path from base_data_path, e.g. "无线/无线-测试题库-杭州.xlsx"
                rel_path = os.path.relpath(os.path.join(root, file), abs_base_data_path)
                
                # dataset name like '无线_无线-测试题库-杭州'
                base_name, _ = os.path.splitext(rel_path)
                name = base_name.replace('/', '_').replace('\\', '_')
                
                infer_cfg = dict(
                    prompt_template=dict(
                        type=PromptTemplate,
                        template='问题：{question}\n请给出回答：',
                    ),
                    retriever=dict(type=ZeroRetriever),
                    inferencer=dict(type=GenInferencer),
                )
                
                eval_cfg = dict(
                    evaluator=dict(type=JiebaRougeEvaluator),
                    pred_role='BOT'
                )

                expert_qa_datasets.append(
                    dict(
                        type=ExpertQADataset,
                        path=base_data_path,
                        name=rel_path,
                        abbr=f'expert_qa-{name}',
                        reader_cfg=dict(
                            input_columns=['question'],
                            output_column='answer',
                            test_split='test'
                        ),
                        infer_cfg=infer_cfg,
                        eval_cfg=eval_cfg,
                    )
                )
else:
    print(f"WARNING: Expert QA dataset path not found at {abs_base_data_path}")
