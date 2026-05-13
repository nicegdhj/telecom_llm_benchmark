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
请基于以下三项输入，对模型的表现进行严格打分：
-原始任务数据（输入）：{original_prompt}（包含告警列表、拓扑关系）。

-参考答案：{reference}。

-模型预测结果（Output）：{prediction}（包含 <think> 思考过程和最终报告）。

从以下三个维度进行打分。

### 评分维度：
1. 聚类准确率[0-5分]
- 评估核心：对比预测分组与参考答案的集合重合度。
- 5分：聚类成员完全一致，无漏分、无误分。
- 3-4分：主要告警已聚合，但存在 1-2 条次要告警未入组。
- 1-2分：核心告警出现分裂，或将两个无关的故障域强行合并。
- 0分：未能识别出核心故障簇，或聚类逻辑与网络拓扑完全脱节。
2. 根因准确率[0-5分]
- 评估核心：遵循“故障源头优先”与“协议栈自底向上”双原则。
- 判定基准：根因必须是导致其他告警产生的源头（如：光缆中断导致的高层业务告警）。
- 0分项：如果模型选定的根因在逻辑上是其他告警的结果，或选定的根因告警根本不在原始数据中，此项直接 0 分。
3. 幻觉检查与逻辑一致性[0-5分]
- 逻辑自洽：检查 <think> 过程是否能支撑最终结论，且绝对忠于原始数据。
- 5分：完全基于事实，推导严丝合缝，没有编造任何实体或关系。
- 1-4分：推导逻辑跳跃，但结论侥幸正确；或存在细微描述瑕疵。
- 0分：发现任何实体幻觉（原始数据中不存在的网元/端口）或关系幻觉（编造原始数据未标注的拓扑连接）。

### 输出格式要求（JSON）：
请仅输出合法的 JSON 格式，不要包含任何 Markdown 标记（如 ```json），不要输出任何前言、后语或注释。必须严格按照以下结构输出：：
{
  "justification": "具体的扣分理由和改进建议...",
  "hallucination_detected": ["如果有幻觉，列出具体的幻觉点"],
  "scores": { "clustering": 5, "root_cause": 5, "hallucination_check": 0 }
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
