# 任务元数据配置：key -> {alias: 展示名称, category: 能力类别}
# 来源：outputs/评测任务文件名对应.xlsx（B列=alias，D列=category）
# 新增任务时直接在此 dict 追加一行即可。
#
# ALLOWED_TASK_KEYS：平台「任务与数据」页面唯一展示白名单 + 展示顺序，
#   与 run_mixed_benchmark.sh 第 284~304 行的 --tasks / --generic-datasets 保持一致。
#   不在此清单内的任务（即使数据库已存在）一律不展示。

TASK_META: dict[str, dict[str, str]] = {
    # ── 通用任务 ────────────────────────────────────────────────────
    "alarm_data_gen_0_shot":              {"alias": "告警聚类降噪",               "category": "运维-告警聚类"},
    "ceval_gen_0_shot_str":               {"alias": "C-Eval",                    "category": "知识类"},
    "mmlu_redux_gen_5_shot_str":          {"alias": "MMLU-Redux",                "category": "知识类"},
    "gpqa_gen_0_shot_str":                {"alias": "GPQA-Diamond",              "category": "推理类"},
    "bbh_gen_3_shot_cot_chat":            {"alias": "BBH（Big-Bench Hard）",     "category": "推理类"},
    "BFCL_gen_simple":                    {"alias": "BFCL v3-单轮任务子集",      "category": "推理类"},
    "ifeval_0_shot_gen_str":              {"alias": "IFEval strict prompt",       "category": "生成类"},
    "math500_gen_0_shot_cot_chat_prompt": {"alias": "MATH 500",                  "category": "数学与代码类"},
    "aime2025_gen_0_shot_chat_prompt":    {"alias": "AIME-2025",                 "category": "数学与代码类"},
    # ── 垂类通用 ────────────────────────────────────────────────────
    "tele_exam_gen_0_shot":               {"alias": "通信工程师中级考试真题-选择题", "category": "知识问答"},
    "tele_exam_gen_0_shot_str":           {"alias": "通信工程师中级考试真题-主观题", "category": "知识问答"},
    "telemath_gen_0_cot_shot":            {"alias": "通信领域数学问题",            "category": "知识问答"},
    "teleqna_gen_0_shot":                 {"alias": "TeleQnA",                   "category": "知识问答"},
    "tspec_gen_0_shot":                   {"alias": "TSpec-LLM",                 "category": "知识问答"},
    "teledata_gen_0_shot":                {"alias": "Tele-Data",                 "category": "知识问答"},
    "telequad_gen_0_shot":                {"alias": "TeleQuAD",                  "category": "知识问答"},
    "opseval_gen_0_shot":                 {"alias": "OpsEval",                   "category": "知识问答"},
    "exam_gen_0_shot":                    {"alias": "通信工程考试（动态多套）",     "category": "知识问答"},
    "identity_gen_0_shot":                {"alias": "身份认知探索",               "category": "安全-身份认知"},
    # ── 垂类自定义任务 ───────────────────────────────────────────────
    "task_1_suite":   {"alias": "家庭支撑智能体-数据自服务-意图识别与工具信息提取", "category": "意图理解-工具调用"},
    "task_34_suite":  {"alias": "政企支撑智能体-意图网关-意图识别",               "category": "意图理解-分类"},
    "task_36_suite":  {"alias": "安全管理智能体-网络安全告警研判",                "category": "意图理解-分类"},
    "task_43_suite":  {"alias": "核心网运维智能体-基础语音投诉工单分类",          "category": "意图理解-分类"},
    "task_44_suite":  {"alias": "核心网运维智能体-基础语音投诉工单提参",          "category": "意图理解-关键信息抽取"},
    "task_60_suite":  {"alias": "投诉调度智能体-是否省内网络投诉",               "category": "意图理解-分类"},
    "task_101_suite": {"alias": "专业知识问答-综合知识型",                       "category": "知识问答"},
    "task_102_suite": {"alias": "多专业知识问答-传输/核心网/集客/家客知识型",     "category": "知识问答"},
}


# 「任务与数据」页面展示白名单 + 顺序（对齐 run_mixed_benchmark.sh 284~304 行）
ALLOWED_TASK_KEYS: list[str] = [
    # 自定义任务（--tasks 1 34 36 43 44 60 101 102）
    "task_1_suite", "task_34_suite", "task_36_suite", "task_43_suite",
    "task_44_suite", "task_60_suite", "task_101_suite", "task_102_suite",
    # 通用数据集（--generic-datasets 顺序）
    "alarm_data_gen_0_shot", "ceval_gen_0_shot_str", "mmlu_redux_gen_5_shot_str",
    "teledata_gen_0_shot", "gpqa_gen_0_shot_str", "bbh_gen_3_shot_cot_chat",
    "BFCL_gen_simple", "ifeval_0_shot_gen_str", "math500_gen_0_shot_cot_chat_prompt",
    "aime2025_gen_0_shot_chat_prompt", "telemath_gen_0_cot_shot", "teleqna_gen_0_shot",
    "tspec_gen_0_shot", "telequad_gen_0_shot", "tele_exam_gen_0_shot",
    "tele_exam_gen_0_shot_str", "opseval_gen_0_shot", "identity_gen_0_shot",
    "exam_gen_0_shot",
]

# key -> 展示序号，供后端排序用
TASK_ORDER: dict[str, int] = {k: i for i, k in enumerate(ALLOWED_TASK_KEYS)}
