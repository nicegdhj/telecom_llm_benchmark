from ais_bench.benchmark.openicl.icl_prompt_template.task_106_prompt_template import Task106PromptTemplate
from ais_bench.benchmark.openicl.icl_retriever import ZeroRetriever
from ais_bench.benchmark.openicl.icl_inferencer import GenInferencer
from ais_bench.benchmark.datasets.custom import CustomDataset
from ais_bench.benchmark.openicl.icl_evaluator.task_105_session_evaluator import Task105SessionEvaluator

SYSTEM_INSTRUCTION = """接下来我会给你发若干个文本，请你从我新发的文本和历史所有文本中(优先考虑新文本的信息)，回答下面的问题：

    ## 判断我的问题是属于哪个业务类别？请从以下选择：
    宽带密码重置:宽带账号密码重置
    宽带密码修改:宽带账号密码修改,密码同步, 改1-6
    查询宽带受理人员和渠道:查询宽带受理人、办理人和渠道,受理组织,受理记录,受理营业厅,营销组织
    查询宽带极光和普通类型:大小猫查询、网关查询、光猫类型、ONU类型、宽带类型
    查询宽带注册码:用户需要查询注册码,查询激活码,查询认证码，注意不是注册卡
    查询摄像头装机类型:询问摄像头的SN, 装机设备类型；安心包设备机型；阳光厨房、云台、室内或室外、安心包、和慧眼
    查询宽带出库的设备序列号:查询设备序列号, sn码, 设备码
    查询路由器终端模式:查询路由器档位,甲供还是乙供,组网模式,组网串号
    查询宽带账号:根据手机号、机顶盒账号、序列号查询宽带账号，宽带查询，宽带账户, 查宽带, 查账号, 查关联账号，注意不能查手机号或联系号码
    查询宽带工单报结状态:查询宽带工单报结状态,是否办结,竣工,报了没
    查询宽带撤单和退单记录:查询宽带撤单、退单记录
    查询光功率值:看数据或者看光, 只有一个光字,光功率查询
    查询机顶盒账号:查机顶盒账号,宽带电视,电视的账号或密码,查7开头账号,机顶盒
    查询宽带3A及在线信息:掉线记录，上网记录，上线记录,下线记录
    工单派发:通常是将单子派发给某个电话, 关键词是 派、单、转
    开端口:指开通光功率，开光猫，激活ONU，激活或重启,猫开下, 网关重启
    签收码查询:只要包含签收、验证码、交付码、竣工码等相似关键字的都选这个。
    用户配置端口查询:端口查询，查询端口信息（olt设备、分光器端口、分光器查询, 端口查询），光交信息，用户配置信息，查资管，分光器,查汇聚,查PON,查跳纤,查上联,资源信息,一级,资源点,哪个箱子,查端口
    分纤箱位置查询:查询附近分纤箱位置
    插拔网纤:查询pon口光功率，IP端口的光功率,PON口下用户上下线实时动态
    随销推荐:随销推荐标签，销售，推销产品
    修改机顶盒密码:修改机顶盒密码, 7开头的账号，注意不是查询机顶盒密码而是修改机顶盒密码
    踢下线:踢下线
    超级密码查询:超级密码查询
    装维主动领单:派单、挂起、驳回、转我、领单、派我，关键字对象是‘我’,工单发我
    出入库轨迹:查询设备出入库记录、出入库轨迹、设备出入库历史, 关键词是‘出入库’
    查询在途装机类的工单信息:在途工单信息，有单子吗,单子在哪里,单子下来没,查询单,有没有单子,询问单子相关的内容,查询工单号,有没有工单
    查询机顶盒安装时间和渠道:机顶盒安装
    终端溯源查询:溯源,溯源查询，在库已经在网的历时数据
    查宽带账号当前所有在网设备:在网设备，查询终端设备，查询在网终端
    暂不确定:只发了一个账号，或者可能是其他类别，但是不能确定具体是哪个， 就选择这个
    不支持该业务:确定业务不在以上所有类别


    ## 提取文本中包含的账号信息，请从以下选择：
    宽带账号:首字母非v的五位小写字母+八位数字,a+十一位数字
    密码:由六位纯数字组成
    手机号:十一位纯数字
    派发对象手机号:在工单派发的场景下，转给某个对象的手机号
    工单号:ZJ或cp开头的账号
    机顶盒账号:首字母v开头的五位小写字母+九位数字组成,7开头纯数字；
    序列号:数字和大写字母组成
    师傅名字:文本中出现的师傅、人员姓名或派发对象名称

    ## 注意事项

    1.如果用户只是含糊地提到了"XX码”、"码"等词语，而没有明确说明是什么码，只有账号、无法判断具体业务->暂不确定
    2.明确不属于已有业务类别 → 不支持该业务
    3.“派我、转我、领单”且对象是“我” → 装维主动领单,派给具体手机号或具体师傅 → 工单派发
    4.如果涉及到多个业务类别，优先选择文本的第一个。
    5.请注意用户输入可能存在同义词或错别字，请注意识别提取到相关类别。

    请将结果以dict格式返回,不要返回其他任何信息。格式样例{"业务类别":"","信息提取":{}} 请确保你返回是一个没有语法错误的完整python dict"""

task_106_reader_cfg = dict(input_columns=["input"], output_column="output")

task_106_infer_cfg = dict(
    prompt_template=dict(
        type=Task106PromptTemplate,
        template=SYSTEM_INSTRUCTION,
    ),
    retriever=dict(type=ZeroRetriever),
    inferencer=dict(type=GenInferencer),
)

task_106_eval_cfg = dict(
    evaluator=dict(
        type=Task105SessionEvaluator,
        field_config={
            "业务类别": {"match_type": "exact", "weight": 1.0},
            "信息提取": {"match_type": "exact", "weight": 1.0},
        },
        default_match_type="exact",
        return_details=True,
        strict_mode=True,
    ),
)

task_106_datasets = [
    dict(
        type=CustomDataset,
        abbr="task_106",
        path="data/custom_task/task_106.jsonl",
        reader_cfg=task_106_reader_cfg,
        infer_cfg=task_106_infer_cfg,
        eval_cfg=task_106_eval_cfg,
    )
]
