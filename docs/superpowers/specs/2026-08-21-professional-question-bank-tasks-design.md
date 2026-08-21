# 20260821 各专业题库评测任务构建设计

日期：2026-08-21
状态：已确认（范围、评估器、数据转换规则、编号、映射格式均经用户确认）

## 1. 背景与目标

基于 `/Users/jia/MyProjects/pythonProjects/cmcc_cxy/Bprocss/benchmark/mydata/20260821专业题库测试` 下的专业题库数据，为每个数据集构建一个评测任务：

1. 数据集文件统一放在 `data/custom_task/task_NNN.jsonl`（`{"input", "output"}` 每行一条）
2. 为每个数据集配套评估算子 `ais_bench/benchmark/configs/datasets/custom_task/task_NNN_suite.py`
3. 生成数据映射关系文档（数据集名 → task_NNN）

## 2. 构建范围（已确认）

范围限定为进度跟踪表第 2、3 行对应的能力：**知识理解（8 个专业）+ 意图识别（3 个专业）= 11 个任务**。
诊断分析 / 自主规划 / 参数提取 的文件本次不构建。

| task | 数据集名 | 源文件（mydata/20260821专业题库测试/…） | 列结构 |
|------|---------|----------------------------------------|--------|
| task_201 | 资源管理-知识理解 | 资源管理/基础题库/资源管理-知识理解（问题-input, 答案-output）.xlsx | 样例/提示词/问题/答案 |
| task_202 | 传输网-知识理解 | 传输网/基础题库/传输-知识理解.xlsx | 编号/问题/答案 |
| task_203 | 代维-知识理解 | 代维/基础题库/代维-知识理解.xlsx | 样例/提示词/问题/答案 |
| task_204 | 个人业务-知识理解 | 个人业务/基础题库/个人业务-知识理解.xlsx | 样例/提示词/问题/答案 |
| task_205 | 核心网-知识理解 | 核心网/基础题库/核心网-知识理解.xlsx | 样例/提示词/问题/答案/组名/贡献人 |
| task_206 | 基础保障-知识理解 | 基础保障/基础题库/基础保障-知识理解.xlsx | 样例/提示词/问题/答案 |
| task_207 | 监控排障-知识理解 | 监控排障/基础题库/监控-知识理解.xlsx | 样例/提示词/问题/答案 |
| task_208 | 网络投诉-知识理解 | 网络投诉/基础题库/监控（投诉）-知识理解.xlsx | 类型/input/output |
| task_209 | 个人业务-意图识别 | 个人业务/基础题库/个人业务-意图识别.xlsx | 样例/提示词/问题/答案 |
| task_210 | 核心网-意图识别 | 核心网/基础题库/核心网-意图识别.xlsx | 编号/提示词/问题/答案 |
| task_211 | 监控排障-意图识别 | 监控排障/基础题库/监控-意图识别.xlsx | 样例/提示词/问题/答案 |

## 3. 数据转换规则

每个 xlsx → `data/custom_task/task_NNN.jsonl`，每行：

```json
{"input": "<问题>", "output": "<答案>"}
```

- 统一取 `问题 → input`、`答案 → output`；网络投诉文件列名即为 `input/output`，直接取用；传输网文件列名为 `编号/问题/答案`，取 `问题/答案` 两列。
- 行校验：跳过表头（首行按表头特征识别）、跳过整行为空的行；`strip()` 清理字段首尾空白；跳过 `问题` 或 `答案` 为空的行。
- 提示词处理（用户已确认）：**有真实提示词的文件**，将提示词硬编码为 suite 的 `SYSTEM_INSTRUCTION`；**无提示词（样例/提示词列为 "/" 或空）的文件不设 SYSTEM_INSTRUCTION**。
  - 有提示词：task_203（"请选择唯一正确选项"）、task_206（选择题任务说明）、task_209、task_210、task_211。
  - 无提示词：task_201、task_202、task_204、task_205、task_207、task_208。
- 计数：以实际文件数据行数为准（进度跟踪表仅作参考），完成后在映射文档中记录每任务实际条数。

## 4. 评估器矩阵（已确认）

| task | 数据集名 | 答案格式 | 评估器 | 参考任务 |
|------|---------|---------|--------|---------|
| task_201–208 | 各专业知识理解 | 长文本/选择题 | TelecomLLMJudgeEvaluator | task_101 |
| task_209 | 个人业务-意图识别 | JSON {intent, entities} | JsonFieldEvaluator（intent 权重 1.0，entities 权重 0） | task_1/60 |
| task_210 | 核心网-意图识别 | JSON {分类结果, 分类标号} | JsonFieldEvaluator | task_43 |
| task_211 | 监控排障-意图识别 | 短分类词 | AccEvaluator | task_34 |

- 知识理解统一用 LLM Judge：答案是非结构化长文本，需语义判分；打分模型走 `SCORE_*` 环境变量（.env.example 已配置）。
- 意图识别用规则型评估器：输出为结构化 JSON 或固定类别，规则判定快且无需额外打分成本。

## 5. 交付物

1. `data/custom_task/task_201.jsonl` … `task_211.jsonl`（11 个数据文件）
2. `ais_bench/benchmark/configs/datasets/custom_task/task_201_suite.py` … `task_211_suite.py`（11 个 suite，含 reader/infer/eval 配置）
3. `docs/20260821专业题库任务映射.md`（数据集名 ↔ task_NNN 映射表，含源文件、能力、评估器、实际条数）

## 6. 验证

- 每个 jsonl 均可被 `CustomDataset.load` 解析（逐行 JSON 合法、`input`/`output` 非空、条数与统计一致）。
- suite 可被 `ais_bench --datasets task_NNN_suite` 识别（导入无异常，`task_NNN_datasets` 导出）。
- 随机抽样若干条核对 input/output 与源 xlsx 一致。
- 报告每任务实际条数，与进度跟踪表数量对比标注差异。
