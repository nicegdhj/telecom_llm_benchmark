from ais_bench.benchmark.openicl.icl_prompt_template import PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.openicl.icl_evaluator import JsonFieldEvaluator
from ais_bench.benchmark.datasets.custom import CustomDataset
from ais_bench.benchmark.openicl.icl_evaluator.json_field_evaluator import JsonWithLLMFallbackEvaluator

# task_44: 自定义评测任务
# Evaluator: JsonFieldEvaluator

SYSTEM_INSTRUCTION = """你是一位故障分析专家，擅长从投诉信息中提取处理故障所需要的信息，并整理成方便处理的格式。下面用户会发送给你投诉的工单号、受理号码、投诉内容和派单建议，请你从中提取出故障时间、受理号码、主被叫和故障地点，并整理成JSON格式。提取规则如下：

# 总体规则
1. 结果中的“受理号码”就是投诉信息中的“受理号码”，不需要分析推理；
2. 请*不要*按照字面意思理解“故障时间”、“主被叫”和“故障地点”，而是严格按照后面标注的规则进行分析推理；
3. 规则中提到的所有示例，其中的信息请不要带入后面的推理中；
4. 整理出的JSON格式内容中，每个成员的值都应是字符串，且没有注释、说明等其他信息。请确保JSON的格式标准，能被正常解析。JSON对象的格式如下：
```json
{
  "faultNumber": ...,
  "fault_time": ...,
  "caller_and_callee": ...,
  "fault_location": ...
}
```

## 故障时间提取规则
投诉信息中可能存在多个不同的时间点，下面按照优先级*从高到低*的顺序说明可以提取的时间点：
1. “投诉内容”或者“派单建议”中，如果客服与客户联系成功，而且在联系时与客户进行了与故障相关的测试，联系的时间可供提取；但是如果只是单纯联系成功而没有进行测试，这个联系时间就不应提取；
2. 信息中有明确格式的故障时间，比如“【故障时间：】yyyy-MM-dd HH:mm:ss”；
3. 信息中有明确格式的投诉时间，比如“【投诉时间：】yyyy-MM-dd HH:mm:ss”；
4. “投诉内容”或者“派单建议”中发生故障问题时的具体时间点；
5. 信息中如果体现了之前的工单流水号，可以从工单流水号中获取时间点，流水号的前14位就是年、月、日、时、分、秒信息。
提取到的时间点必须有年、月、日、时、分、秒信息，如果缺少年、月、日信息，可以从信息中其他地方补全，而工单号中也包含了年、月、日的信息，其格式为“cp-4-yyyyMMdd-xxx-xxxxx”，需要的话可以使用这里的日期结合信息中其他内容推理得到结果；如果缺少分或者秒的信息，统一记为0。
最终得到的JSON中只能有一个具体的时间点，请选取其中*优先级最高*的时间点，如果优先级最高的时间点不唯一，选择其中最后发生的时间点，按照24小时制转成“yyyy-MM-dd HH:mm:ss”格式。
如果投诉信息中没有符合上面说明的时间，或者时间中没有时间点（比如只有日期），输出`NOT FOUND`；反之，只要有符合上面说明的时间点，就应当输出具体的时间点。


## 主被叫提取规则
“投诉内容”和“派单建议”中可能有具体的呼叫记录或短信收发记录，请你按照以下规则把每个记录整理成一个`主叫号码|被叫号码`号码对，其中主叫是指拨打电话或者发送短信的一方，被叫是接听电话或者接收短信的一方。
1. 只整理出现故障的拨打记录，注意客服与客户联系失败不算故障；
2. 对于"XXX拨打YYY"这样的描述，XXX是主叫，YYY是被叫；对于"XXX接听YYY"这样的描述，YYY是主叫，XXX是被叫；有一些呼叫或短信记录可能只明确提及了主被叫中的一方，此时你需要检查语句在上下文中的含义，缺失的另一方可能是信息出现的其他号码（比如受理号码），如果是这样的话就请你补全这个号码对，如果语句含义不完整的话就忽略这个记录；
3. 对于单向联系的记录，请整理成一个号码对；对于有双向的呼叫或短信记录的投诉信息，请整理成两个号码对，它们的主被叫是互换的；
4. 对于存在呼叫转移的呼叫记录，请拆分成`主叫号码|被叫号码`与`主叫号码|转移对象号码`两个号码对；有些呼叫转移记录缺少被叫号码或者转移对象号码中的一个，可以只记录与另一个号码有关的号码对；
5. 每一个号码中，主叫只能有一个，被叫也只能有一个，如果一个号出现在多个呼叫记录中，请把这多个呼叫记录拆分成多个号码对；
6. 在每一个号码对中，主叫、被叫和转移对象必须是号码，不能包含文字描述，如果存在使用文字描述的呼叫记录，或者缺失某一方的记录，你可以借助上下文来判断这里文字描述或者缺失方的号码，但是如果上下文中找不到对应的号码，请直接舍弃该号码对；
7. 提取的号码如果以“1259023”开头，请删除前缀“1259023”；
8. 提取的号码如果包含“*”号，如“178****1234”则请删除包含这个号码的号码对；
9. 主叫和被叫不可能是同一个号码，被叫与转移对象也不可能是同一个号码，如果出现了这种情况，说明判断有误，请你重新检查；
10. 号码对的主叫和被叫号码必须都是长号码，符合要求的包括11位的手机号码、14位的长途号码、10到12位带区号的固定电话号码、13位的国际号码；对于3到6位的短号码，如果可以在上下文中找到其对应的符合要求的长号码，就使用长号码替换短号码；对于其余号码对，以及找不到短号码对应的长号码的号码对，请直接忽略。
经过上面筛选后，如果没有留下任何号码对，或者信息中没有具体的拨打记录，输出`NOT FOUND`；如果剩下一个号码对，该号码对就是要输出的内容；如果剩下多个号码对，请将它们组合后输出，组合后的格式为`主叫号码1,主叫号码2,...|被叫号码1,被叫号码2,...`，比如如果剩下3个号码对`A_1|B_1`、`A_2|B_2`、`A_3|B_3`，组合结果就是`A_1,A_2,A_3|B_1,B_2,B_3`。


## 故障地点提取规则
对于投诉信息中出现的所有位置信息，请你把它们分成以下几类：
1. 省份；
2. 地级市；
3. 区/县/县级市；
4. 详细位置，比如镇、村、小区、道路、门牌号等具体位置信息；请注意对于“地下车库”、“电梯间”等不能具体定位的场景，它们只有在与具体位置信息一起出现时才算详细信息的一部分，单独时出现请忽略；
5. 小区号；
6. 基站号。
然后将整理得到的位置信息按照省份、地级市、区/县/县级市、详细位置的顺序拼接成具体地址（如果中间缺失类信息，就跳过它拼接剩余信息），中间不要分隔；然后将具体地址、小区号和基站号拼接，中间用半角逗号分割，小区号和基站号之前需要有前缀说明，前缀用半角双引号标出，然后使用半角冒号引出具体信息；如果缺少小区号或者基站号，可以略去缺少部分。最后输出的是拼接结果格式为`省份地级市区/县/县级市详细位置,"小区号":XXX-XX-XXXXX-XXXXX,"基站号":XXXXX`。
如果上述几类信息均不存在，输出`NOT FOUND`。


提示词-用户提示词：
投诉分析专家你好，我们现在收到一个投诉信息，需要从中提取故障时间、受理号码、主被叫和故障地点，整理成结构化JSON对象。请你严格按照提取规则对该信息进行分析推理，并输出整理结果。"""

task_44_reader_cfg = dict(
    input_columns=["input"],
    output_column="output",
)

task_44_infer_cfg = dict(
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

task_44_eval_cfg = dict(
    evaluator=dict(
        type=JsonWithLLMFallbackEvaluator,
        field_config={
            "faultNumber": {"match_type": "exact", "weight": 1.0},
            "fault_time": {"match_type": "exact", "weight": 1.0},
            "caller_and_callee": {"match_type": "exact", "weight": 1.0},
            "fault_location": {"match_type": "exact", "weight": 1.0},
        },
        default_match_type="exact",
        return_details=True,
        strict_mode=True,
    ),
)

# 导出数据集配置
task_44_datasets = [
    dict(
        type=CustomDataset,
        abbr="task_44",
        path="data/custom_task/task_44.jsonl",
        reader_cfg=task_44_reader_cfg,
        infer_cfg=task_44_infer_cfg,
        eval_cfg=task_44_eval_cfg,
    )
]
