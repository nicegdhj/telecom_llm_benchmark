from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import AccEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset

# task_107: 网络安全告警研判
# 场景: 安全管理智能体-网络安全告警研判
# Metric: ACC（判断是否为 web attack，输出 Yes/No）

# 该任务固定的系统提示词
SYSTEM_INSTRUCTION = """Act as a cybersecurity analyst who is skilled in identifying and assessing potential threats in textual data.
Please analyze the following request payload to determine if it represents a web attack.Respond only with 'Yes' if it is a web attack, or 'No' if it is not.

Pay attention to some edge cases

1. If a login, authentication, admin, or root endpoint carries a non-empty
plaintext password, especially admin/root with a weak password, classify the
request as Yes.

2. Treat the following image-thumbnail requests as No when they only reference
a normal image file and contain no other explicit attack indicators:
- /images.php with filename=../pic/...<image> and numeric width/height
- /include/thumb.php with dir=../upload/...<image> and numeric x/y

A .php endpoint or a relative path such as ../pic/ or ../upload/ is not by
itself sufficient evidence of an attack.

Here is the given payload of the request:
{}
"""

task_107_reader_cfg = dict(
    input_columns=["input"],
    output_column="output",
)

task_107_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=dict(
            begin=[
                dict(role="SYSTEM", fallback_role="HUMAN", prompt=SYSTEM_INSTRUCTION),
            ],
            round=[
                dict(role="HUMAN", prompt="{input}"),
                dict(role="BOT", prompt=""),
            ],
        ),
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

task_107_eval_cfg = dict(
    evaluator=dict(type=AccEvaluator),
)

# 导出数据集配置
task_107_datasets = [
    dict(
        type=CustomDataset,
        abbr="task_107",
        path="data/custom_task/task_107.jsonl",
        reader_cfg=task_107_reader_cfg,
        infer_cfg=task_107_infer_cfg,
        eval_cfg=task_107_eval_cfg,
    )
]
