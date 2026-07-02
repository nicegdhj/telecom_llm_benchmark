from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import JsonFieldEvaluator
from ais_bench.benchmark.datasets.custom import Task1Dataset

# 硬编码系统提示词（来自 task_1.jsonl 数据中的 system 字段）
SYSTEM_INSTRUCTION = """
接下来我会给你发若干个文本，请你作为支撑助手，从我新发的文本和历史所有文本中，优先考虑新文本的信息，回答下面的问题：

1.判断我的问题是属于哪个业务类别？请从以下列表中选择：["宽带密码重置", "宽带密码修改", "查询宽带受理人员和渠道", "查询宽带极光和普通类型","查询宽带注册码","查询宽带出库的设备序列号", "查询路由器终端模式", "查询摄像头装机类型安心包/和慧眼","查询宽带账号","查询宽带工单报结状态","查询宽带撤单、退单记录","查询光功率值","查询机顶盒账号","查询宽带3A及在线信息","工单派发","激活失败重配","开端口","VLAN数据问题","系统流程及卡单","不支持该业务"]。如果无法确定业务类别，则选择暂不确定。
2.提取文本中包含的账号信息，请从以下列表中选择：{"宽带账号":[首字母非v的五位小写字母+8位数字,a+11位数字,],"密码","手机号","工单号","机顶盒账号":[首字母v开头的五位小写字母+9位数字,7开头纯数字,],"sn账号","班组","师傅名字"}。

请将结果以json格式返回, 格式样例{"业务类别":"","信息提取":{}}
"""

task_1_reader_cfg = dict(
    input_columns=["dialog_input"],
    output_column="output",
)

task_1_infer_cfg = dict(
    prompt_template=dict(
        type=PromptTemplate,
        template=dict(
            begin=[
                dict(role="SYSTEM", fallback_role="HUMAN", prompt=SYSTEM_INSTRUCTION),
            ],
            round=[
                dict(role="HUMAN", prompt="{dialog_input}"),
                dict(role="BOT", prompt=""),
            ],
        ),
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

task_1_eval_cfg = dict(
    evaluator=dict(
        type=JsonFieldEvaluator,
        field_config={
            "业务类别": {"match_type": "exact", "weight": 1.0},
            "信息提取": {"match_type": "exact", "weight": 1.0},
        },
        default_match_type="exact",
        return_details=True,
        strict_mode=True,
    ),
)

task_1_datasets = [
    dict(
        type=Task1Dataset,
        abbr="task_1",
        path="data/custom_task/task_1.jsonl",
        reader_cfg=task_1_reader_cfg,
        infer_cfg=task_1_infer_cfg,
        eval_cfg=task_1_eval_cfg,
    )
]
