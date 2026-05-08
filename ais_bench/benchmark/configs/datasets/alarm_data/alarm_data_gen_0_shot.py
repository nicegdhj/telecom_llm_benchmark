from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.datasets import AlarmDataDataset
from ais_bench.benchmark.openicl.icl_evaluator import AlarmJudgeEvaluator

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
        type=AlarmJudgeEvaluator,
        prompt_template="""## 你是一个 AIOps 专家评估系统。你具备深厚的网络拓扑逻辑、告警传播链分析以及模型评估经验。
请基于以下三项输入，对模型的表现进行打分：
原始任务数据（输入）：{original_prompt}（包含告警列表、拓扑关系）。

参考答案：{reference}。

模型预测结果（Output）：{prediction}（包含 <think> 思考过程和最终报告）。

从以下三个维度进行打分。

### 评分维度：
1. 聚类准确率 (Clustering Fidelity) [0-10分]
评估核心：对比预测分组与 GT 的集合重合度。
评分阶梯：
10分：聚类成员完全一致，无漏分、无误分。
7-9分：主要告警已聚合，但存在 1-2 条次要告警（如非关键通知）未入组。
4-6分：核心告警出现分裂，或将两个无关的故障域强行合并。
0分：未能识别出核心故障簇，或聚类逻辑与网络拓扑完全脱节。
2. 根因准确率 (Root Cause Precision) [0-10分]
评估核心：基于“传播链起始点”与“物理层级最低点”原则。
判定基准：
根因必须是导致其他告警产生的源头（如：光缆中断导致的高层业务告警）。
0分项：如果模型选定的根因在逻辑上是其他告警的结果，或选定的根因告警根本不在原始数据中，此项直接 0 分。
3. 幻觉检查与逻辑一致性 [0-10分]
逻辑自洽：检查 <think> 过程是否能支撑最终结论。严禁出现“推导是 A，结论是 B”的情况。
幻觉红线（一票否决）：
实体幻觉：严禁出现原始数据中不存在的网元、端口。
关系幻觉：严禁编造拓扑连接。如果模型声称 A 和 B 有连接但原始数据未标注，视为严重幻觉。
评分阶梯：
10分：完全基于事实，推导严丝合缝。
1-5分：推导逻辑跳跃，但结论侥幸正确；或存在细微描述瑕疵。
0分：发现任何实体幻觉或编造拓扑连接。

### 输出格式（JSON）：
请输出如下格式的评分结果：
{
  "scores": { "clustering": 8, "root_cause": 10, "hallucination_check": 0 },
  "justification": "具体的扣分理由和改进建议...",
  "hallucination_detected": ["如果有幻觉，列出具体的幻觉点"]
}
"""
    ),
)

alarm_data_datasets = [
    dict(
        abbr="alarm_data",
        type=AlarmDataDataset,
        path="data/alarm_data/test_data.json",
        name="alarm_data",
        reader_cfg=alarm_data_reader_cfg,
        infer_cfg=alarm_data_infer_cfg,
        eval_cfg=alarm_data_eval_cfg,
    )
]
