from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import JsonFieldEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_209: 个人业务-意图识别
# Metric: JsonFieldEvaluator
# 该任务固定的系统提示词（取自源文件提示词列众数）
SYSTEM_INSTRUCTION = "你是业务平台工作台智能助手的意图识别模块。请识别用户输入的意图类型并抽取关键实体。意图类型：query_function（功能咨询）、query_indicator（指标咨询）、operation_request（操作请求）、data_query（数据查询）、flow_inquiry（流程咨询）、compare_inquiry（对比咨询）、api_inquiry（API咨询）、security_inquiry（安全咨询）、platform_inquiry（平台纳管咨询）、fault_analysis（故障分析请求）。输出严格JSON：intent、entities、confidence。"

task_209_reader_cfg = dict(
    input_columns=['input'],
    output_column='output',
)

task_209_infer_cfg = dict(
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

task_209_eval_cfg = dict(
    evaluator=dict(
        type=JsonFieldEvaluator,
        field_config={'intent': {'match_type': 'exact', 'weight': 1.0},
 'entities': {'match_type': 'exact', 'weight': 0.0}},
        default_match_type='exact',
        return_details=True,
        strict_mode=True,
    ),
)

# 导出数据集配置
task_209_datasets = [
    dict(
        type=CustomDataset,
        abbr='task_209',
        path='data/custom_task/task_209.jsonl',
        reader_cfg=task_209_reader_cfg,
        infer_cfg=task_209_infer_cfg,
        eval_cfg=task_209_eval_cfg,
    )
]
