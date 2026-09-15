# 任务元数据配置：key -> {alias: 展示名称, category: 能力类别}
# 来源：outputs/评测任务文件名对应.xlsx（B列=alias，D列=category）
# 新增任务时直接在此 dict 追加一行即可。
#
# ALLOWED_TASK_KEYS：平台「任务与数据」页面唯一展示白名单 + 展示顺序，
#   与 run_mixed_benchmark.sh 的 --tasks / --generic-datasets 保持一致。
#   不在此清单内的任务（即使数据库已存在）一律不展示。

TASK_META: dict[str, dict[str, str]] = {
    # ── 通用任务 ────────────────────────────────────────────────────
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
    # ── 公开通信题库 ────────────────────────────────────────────────
    "ot_3gpp_tsg":    {"alias": "ot_3gpp_tsg",    "category": "公开通信题库"},
    "ot_oranbench":   {"alias": "ot_oranbench",   "category": "公开通信题库"},
    "ot_sixg_bench":  {"alias": "ot_sixg_bench",  "category": "公开通信题库"},
    "ot_srsranbench": {"alias": "ot_srsranbench", "category": "公开通信题库"},
    "ot_telelogs":    {"alias": "ot_telelogs",    "category": "公开通信题库"},
    "ot_telemath":    {"alias": "ot_telemath",    "category": "公开通信题库"},
    "ot_teleqna":     {"alias": "ot_teleqna",     "category": "公开通信题库"},
    "ot_teletables":  {"alias": "ot_teletables",  "category": "公开通信题库"},
    # ── 20260908 专业题库（非合并，单数据集）─────────────────────────
    "task_201_suite": {"alias": "资源管理-知识理解",               "category": "知识理解"},
    "task_202_suite": {"alias": "传输网-知识理解",                 "category": "知识理解"},
    "task_203_suite": {"alias": "代维-知识理解",                   "category": "知识理解"},
    "task_204_suite": {"alias": "个人业务-知识理解",               "category": "知识理解"},
    "task_205_suite": {"alias": "核心网-知识理解",                 "category": "知识理解"},
    "task_206_suite": {"alias": "基础保障-知识理解",               "category": "知识理解"},
    "task_207_suite": {"alias": "监控排障-知识理解",               "category": "知识理解"},
    "task_208_suite": {"alias": "网络投诉-知识理解",               "category": "知识理解"},
    "task_211_suite": {"alias": "监控排障-意图识别",               "category": "意图识别"},
    "task_212_suite": {"alias": "家客-知识理解",                   "category": "知识理解"},
    "task_213_suite": {"alias": "集客-知识理解",                   "category": "知识理解"},
    "task_215_suite": {"alias": "监控排障-参数提取",               "category": "参数提取"},
    "task_216_suite": {"alias": "个人业务-自主规划",               "category": "自主规划"},
    "task_217_suite": {"alias": "代维-自主规划",                   "category": "自主规划"},
    "task_218_suite": {"alias": "监控排障-自主规划",               "category": "自主规划"},
    "task_219_suite": {"alias": "网络投诉-自主规划",               "category": "自主规划"},
    "task_220_suite": {"alias": "资源管理-自主规划",               "category": "自主规划"},
    "task_221_suite": {"alias": "个人业务-诊断分析",               "category": "诊断分析"},
    "task_222_suite": {"alias": "代维-诊断分析",                   "category": "诊断分析"},
    "task_223_suite": {"alias": "传输网-诊断分析",                 "category": "诊断分析"},
    "task_224_suite": {"alias": "基础保障-诊断分析",               "category": "诊断分析"},
    "task_226_suite": {"alias": "监控排障-诊断分析",               "category": "诊断分析"},
    "task_227_suite": {"alias": "资源管理-诊断分析",               "category": "诊断分析"},
    "task_234_suite": {"alias": "入口智能体-测试集",               "category": "入口智能体"},
    "task_235_suite": {"alias": "安全-诊断分析",                   "category": "诊断分析"},
    "task_247_suite": {"alias": "家客-诊断分析",                   "category": "诊断分析"},
    # ── 20260908 专业题库（合并，多子数据集汇聚）────────────────────
    "task_209_suite": {"alias": "个人业务-意图识别",               "category": "意图识别"},
    "task_210_suite": {"alias": "核心网-意图识别-分类",            "category": "意图识别"},
    "task_214_suite": {"alias": "个人业务-参数提取",               "category": "参数提取"},
    "task_225_suite": {"alias": "核心网-诊断分析",                 "category": "诊断分析"},
    "task_229_suite": {"alias": "核心网-意图识别-参数提取",        "category": "意图识别"},
    "task_236_suite": {"alias": "家客-意图识别+信息提取",          "category": "意图识别"},
    "task_240_suite": {"alias": "家客-意图识别-分类",              "category": "意图识别"},
    "task_250_suite": {"alias": "网络投诉-信息提取",               "category": "参数提取"},
    "task_253_suite": {"alias": "网络投诉-意图识别",               "category": "意图识别"},
    "task_256_suite": {"alias": "集客-参数提取",                   "category": "参数提取"},
    "task_258_suite": {"alias": "集客-意图识别",                   "category": "意图识别"},
    "task_260_suite": {"alias": "集客-诊断分析",                   "category": "诊断分析"},
}


# 「任务与数据」页面展示白名单 + 顺序
ALLOWED_TASK_KEYS: list[str] = [
    # 自定义任务
    "task_1_suite", "task_34_suite", "task_36_suite", "task_43_suite",
    "task_44_suite", "task_60_suite", "task_101_suite", "task_102_suite",
    # 非合并 task_2xx（单数据集）
    "task_201_suite", "task_202_suite", "task_203_suite", "task_204_suite",
    "task_205_suite", "task_206_suite", "task_207_suite", "task_208_suite",
    "task_211_suite", "task_212_suite", "task_213_suite", "task_215_suite",
    "task_216_suite", "task_217_suite", "task_218_suite", "task_219_suite",
    "task_220_suite", "task_221_suite", "task_222_suite", "task_223_suite",
    "task_224_suite", "task_226_suite", "task_227_suite",
    "task_234_suite", "task_235_suite", "task_247_suite",
    # 合并 task_2xx（多子数据集汇聚）
    "task_209_suite", "task_210_suite", "task_214_suite", "task_225_suite",
    "task_229_suite", "task_236_suite", "task_240_suite", "task_250_suite",
    "task_253_suite", "task_256_suite", "task_258_suite", "task_260_suite",
    # 公开通信题库
    "ot_3gpp_tsg", "ot_oranbench", "ot_sixg_bench", "ot_srsranbench",
    "ot_telelogs", "ot_telemath", "ot_teleqna", "ot_teletables",
    # 通用数据集
    "ceval_gen_0_shot_str", "mmlu_redux_gen_5_shot_str",
    "teledata_gen_0_shot", "gpqa_gen_0_shot_str", "bbh_gen_3_shot_cot_chat",
    "BFCL_gen_simple", "ifeval_0_shot_gen_str", "math500_gen_0_shot_cot_chat_prompt",
    "aime2025_gen_0_shot_chat_prompt", "telemath_gen_0_cot_shot", "teleqna_gen_0_shot",
    "tspec_gen_0_shot", "telequad_gen_0_shot", "tele_exam_gen_0_shot",
    "tele_exam_gen_0_shot_str", "opseval_gen_0_shot", "identity_gen_0_shot",
    "exam_gen_0_shot",
]

# key -> 展示序号，供后端排序用
TASK_ORDER: dict[str, int] = {k: i for i, k in enumerate(ALLOWED_TASK_KEYS)}


# 各任务原始评测数据的相对路径（相对代码/数据根目录），用于挂载 init 版本与下载。
# generic 取自各 suite config 的 path；custom 为 data/custom_task/ 或专用目录。
# 路径指向文件 → 打包该文件；指向目录 → 打包整个目录。
TASK_DATA_PATH: dict[str, str] = {
    # ── 通用任务 ──
    "ceval_gen_0_shot_str":               "data/ceval/formal_ceval",
    "mmlu_redux_gen_5_shot_str":          "data/mmlu_redux",
    "teledata_gen_0_shot":                "data/Tele-Data",
    "gpqa_gen_0_shot_str":                "data/gpqa",
    "bbh_gen_3_shot_cot_chat":            "data/BBH/data",
    "BFCL_gen_simple":                    "data/BFCL",
    "ifeval_0_shot_gen_str":              "data/ifeval/input_data.jsonl",
    "math500_gen_0_shot_cot_chat_prompt": "data/math",
    "aime2025_gen_0_shot_chat_prompt":    "data/aime2025/aime2025.jsonl",
    "telemath_gen_0_cot_shot":            "data/TeleMath",
    "teleqna_gen_0_shot":                 "data/teleqna",
    "tspec_gen_0_shot":                   "data/TSpec-LLM",
    "telequad_gen_0_shot":                "data/TeleQuAD",
    "tele_exam_gen_0_shot":               "data/telecom-intermediate-exam",
    "tele_exam_gen_0_shot_str":           "data/telecom-intermediate-exam",
    "opseval_gen_0_shot":                 "data/OpsEval",
    "identity_gen_0_shot":                "data/Identity_Exploration",
    "exam_gen_0_shot":                    "data/exam",
    # ── 垂类自定义任务 ──
    "task_1_suite":   "data/custom_task/task_1.jsonl",
    "task_34_suite":  "data/custom_task/task_34.jsonl",
    "task_36_suite":  "data/custom_task/task_36.jsonl",
    "task_43_suite":  "data/custom_task/task_43.jsonl",
    "task_44_suite":  "data/custom_task/task_44.jsonl",
    "task_60_suite":  "data/custom_task/task_60.jsonl",
    "task_101_suite": "data/custom_task/task_101.jsonl",
    "task_102_suite": "data/task_102",
    # ── 公开通信题库 ──
    "ot_3gpp_tsg":    "data/ot-full/3gpp_tsg/test-00000-of-00001.jsonl",
    "ot_oranbench":   "data/ot-full/oranbench/test-00000-of-00001.jsonl",
    "ot_sixg_bench":  "data/ot-full/sixg_bench/test-00000-of-00001.jsonl",
    "ot_srsranbench": "data/ot-full/srsranbench/test-00000-of-00001.jsonl",
    "ot_telelogs":    "data/ot-full/telelogs/test-00000-of-00001.jsonl",
    "ot_telemath":    "data/ot-full/telemath/test-00000-of-00001.jsonl",
    "ot_teleqna":     "data/ot-full/teleqna/test-00000-of-00001.jsonl",
    "ot_teletables":  "data/ot-full/teletables/test-00000-of-00001.jsonl",
    # ── 20260908 专业题库（非合并，单数据集，jsonl 文件）──
    "task_201_suite": "data/custom_task/task_201.jsonl",
    "task_202_suite": "data/custom_task/task_202.jsonl",
    "task_203_suite": "data/custom_task/task_203.jsonl",
    "task_204_suite": "data/custom_task/task_204.jsonl",
    "task_205_suite": "data/custom_task/task_205.jsonl",
    "task_206_suite": "data/custom_task/task_206.jsonl",
    "task_207_suite": "data/custom_task/task_207.jsonl",
    "task_208_suite": "data/custom_task/task_208.jsonl",
    "task_211_suite": "data/custom_task/task_211.jsonl",
    "task_212_suite": "data/custom_task/task_212.jsonl",
    "task_213_suite": "data/custom_task/task_213.jsonl",
    "task_215_suite": "data/custom_task/task_215.jsonl",
    "task_216_suite": "data/custom_task/task_216.jsonl",
    "task_217_suite": "data/custom_task/task_217.jsonl",
    "task_218_suite": "data/custom_task/task_218.jsonl",
    "task_219_suite": "data/custom_task/task_219.jsonl",
    "task_220_suite": "data/custom_task/task_220.jsonl",
    "task_221_suite": "data/custom_task/task_221.jsonl",
    "task_222_suite": "data/custom_task/task_222.jsonl",
    "task_223_suite": "data/custom_task/task_223.jsonl",
    "task_224_suite": "data/custom_task/task_224.jsonl",
    "task_226_suite": "data/custom_task/task_226.jsonl",
    "task_227_suite": "data/custom_task/task_227.jsonl",
    "task_234_suite": "data/custom_task/task_234.jsonl",
    "task_235_suite": "data/custom_task/task_235.jsonl",
    "task_247_suite": "data/custom_task/task_247.jsonl",
    # ── 20260908 专业题库（合并，多子数据集，目录）──
    "task_209_suite": "data/custom_task/task_209",
    "task_210_suite": "data/custom_task/task_210",
    "task_214_suite": "data/custom_task/task_214",
    "task_225_suite": "data/custom_task/task_225",
    "task_229_suite": "data/custom_task/task_229",
    "task_236_suite": "data/custom_task/task_236",
    "task_240_suite": "data/custom_task/task_240",
    "task_250_suite": "data/custom_task/task_250",
    "task_253_suite": "data/custom_task/task_253",
    "task_256_suite": "data/custom_task/task_256",
    "task_258_suite": "data/custom_task/task_258",
    "task_260_suite": "data/custom_task/task_260",
}
