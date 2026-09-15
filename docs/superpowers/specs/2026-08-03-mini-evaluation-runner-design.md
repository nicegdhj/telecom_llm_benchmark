# Mini Evaluation Runner Design

## Goal

在 `mini_demo` 中提供一个不依赖 `ais_bench` 包的轻量测评工程，直接使用 Python 3.10+ 运行以下四个任务：

- `opseval_gen_0_shot`
- `tele_exam_gen_0_shot`
- `tele_exam_gen_0_shot_str`
- `exam_gen_0_shot`

工程通过 OpenAI 兼容的 HTTP Chat Completions 接口并发推理，保留完整 JSON 结果，按现有任务的评估行为计算准确率或加权得分，并支持后台运行和实时日志查看。

## Scope

### Included

- 读取仓库现有的三个数据目录：`data/OpsEval`、`data/telecom-intermediate-exam`、`data/exam`。
- 复刻四个任务当前使用的数据筛选、Prompt、答案后处理和评分行为。
- 使用 Python 标准库 `urllib.request` 发起 HTTP 请求。
- 使用 `concurrent.futures.ThreadPoolExecutor` 实现可配置并发。
- 首次请求失败后最多重试两次，即单条请求最多尝试三次。
- 推理模型和 LLM Judge 分别支持独立的 URL、API Key、模型名和并发数。
- 输出推理明细、评估明细、汇总指标和运行日志。
- 使用 `run.sh` 提供后台启动、状态查看、日志跟踪和停止能力。

### Excluded

- 不导入或安装 `ais_bench`。
- 不实现 ais_bench 的注册器、配置系统、Retriever 或通用 Inferencer。
- 不增加断点续跑、Web 页面、数据库或分布式任务调度。
- 不把 API Key 写入代码、配置样例、日志或输出 JSON。

## Architecture

### Files

- `mini_demo/mini_eval.py`
  - 命令行入口。
  - 校验参数和环境变量。
  - 调度数据加载、并发推理、评估和结果写入。
  - 输出统一进度日志。
- `mini_demo/task_logic.py`
  - 加载四个任务的数据。
  - 构造与现有配置一致的 Prompt。
  - 实现选择题答案提取、Exam 动态评分和 LLM Judge 结果解析。
- `mini_demo/http_client.py`
  - 规范化 Chat Completions URL。
  - 发送 OpenAI 兼容请求。
  - 实现超时、重试和响应内容提取。
- `mini_demo/run.sh`
  - 提供 `start`、`status`、`logs`、`stop` 子命令。
  - 使用 `nohup`、PID 文件和独立运行目录管理后台进程。
- `mini_demo/README.md`
  - 记录环境变量、参数、前台与后台运行示例、输出结构。
- `mini_demo/tests/test_mini_eval.py`
  - 使用 Python 标准库 `unittest` 验证核心行为。

## Command-Line Interface

前台入口：

```bash
python mini_demo/mini_eval.py \
  --tasks opseval_gen_0_shot tele_exam_gen_0_shot \
  --concurrency 6 \
  --output-dir mini_demo/outputs
```

主要参数：

- `--tasks`：一个或多个任务名；缺省时执行全部四个任务。
- `--concurrency`：推理线程数，默认 `6`。
- `--judge-concurrency`：Judge 线程数，默认继承 `--concurrency`。
- `--max-tokens`：推理最大输出长度，默认 `2048`。
- `--judge-max-tokens`：Judge 最大输出长度，默认 `512`。
- `--timeout`：单次 HTTP 请求超时秒数，默认 `120`。
- `--output-dir`：运行结果根目录，默认 `mini_demo/outputs`。
- `--limit`：每个任务最多执行的样本数，仅用于本地冒烟测试；缺省时执行全量。

模型配置通过环境变量传入：

- `INFER_API_KEY`、`INFER_BASE_URL`、`INFER_MODEL`
- `JUDGE_API_KEY`、`JUDGE_BASE_URL`、`JUDGE_MODEL`

`JUDGE_*` 未配置时逐项继承对应的 `INFER_*`。URL 同时接受 `/v1` 基础地址和完整 `/chat/completions` 地址，内部统一规范化为完整请求地址。

## Data Loading and Prompts

### opseval_gen_0_shot

- 加载 `data/OpsEval` 下的 `5G_Communication.jsonl`、`Mobile_Communication_Network.jsonl` 和 `Wired_NetWork.jsonl`。
- 清理答案末尾空格和逗号，并提取首个答案字母。
- Prompt 保持现有英文选择题模板。

### tele_exam_gen_0_shot

- 只加载 `data/telecom-intermediate-exam/2023/综合/*.json`。
- 标准答案优先使用非空的 `correct answer`，否则使用 `answer`。
- Prompt 要求只输出 `A-D` 选项字母。

### tele_exam_gen_0_shot_str

- 遍历所有年份下的 `传输与接入（无线）`、`互联网技术`、`设备环境` 三个目录。
- 与现有加载器保持一致，答案使用非空 `answer`，否则使用 `correct answer`；`×` 和 `√` 分别规范化为“错误”和“正确”。
- Prompt 要求根据题型简洁作答。
- 每条回答交给通用 LLM Judge，按题目 `score` 计算连续得分。

### exam_gen_0_shot

- 加载 `data/exam` 中配置列出的九套试卷。
- 支持 `multiple_choice`、`fill_blank`、`subjective` 三类题目。
- 跳过 `has_image=true` 或 `need_plot=true` 的题目。
- 根据题型添加与现有加载器一致的作答要求。

## HTTP and Concurrency

每个推理请求提交到线程池，任务之间按顺序运行，任务内部并发。请求体使用 OpenAI Chat Completions 格式：

```json
{
  "model": "configured-model",
  "messages": [
    {"role": "user", "content": "rendered prompt"}
  ],
  "stream": false,
  "max_tokens": 2048,
  "temperature": 0
}
```

重试规则：

- HTTP 非 2xx、网络错误、超时、无有效 `choices[0].message.content` 均视为失败。
- 每次失败后采用短暂递增等待，再重试，最多额外重试两次。
- 最终失败的样本记录 `status=failed`、错误文本和 `attempts=3`，继续处理其他样本。
- 日志和结果中不得包含 Authorization Header 或 API Key。

LLM Judge 使用独立线程池。Judge 请求失败时，该样本标记为 Judge 失败并从连续得分的有效分母中排除，与现有评估器行为一致。

## Evaluation Compatibility

### Choice Accuracy

`opseval_gen_0_shot` 使用 `A-E`、`tele_exam_gen_0_shot` 使用 `A-D`。答案提取优先识别“答案”“最终答案”“Answer”等结论格式，再以首个合法选项字母兜底。准确率为完全匹配数量除以成功推理且存在标准答案的样本数，乘以 100。

### Generic LLM Judge

`tele_exam_gen_0_shot_str` 和 Exam 的填空题、主观题使用现有 `LLMJudgeEvaluator` 的评分口径：

- Judge Prompt 提供题目满分、标准答案和模型答案。
- 接受 JSON `score` 字段、独占一行数字或输出中的最后一个数字。
- 得分限制在 `0` 到题目满分之间。
- Judge 空响应或请求失败不计入最终有效分母。

### Exam Dynamic Scoring

- 选择题支持多空答案，按位置正确比例乘以本题分值。
- 填空题先进行原文、去空格和 LaTeX 排版规范化匹配；未命中时调用 LLM Judge。
- 主观题调用 LLM Judge。
- 每套试卷得分为有效题目所得分之和除以有效题目满分之和，再乘以 100。
- 总体得分使用所有试卷的有效所得分和有效满分统一计算，不对各试卷百分比做简单平均。

## Output

每次运行创建目录：

```text
mini_demo/outputs/<task_id>/
├── run.log
├── run_config.json
├── summary.json
├── opseval_gen_0_shot.json
├── tele_exam_gen_0_shot.json
├── tele_exam_gen_0_shot_str.json
└── exam_gen_0_shot.json
```

`run_config.json` 保存去除 API Key 后的运行参数和模型信息。每个任务 JSON 包含：

- `task`、`started_at`、`finished_at`
- `metrics`
- `samples`

每条 sample 至少保存：

- 样本标识、子数据集或试卷名、题目类型、Prompt、标准答案。
- 推理状态、尝试次数、模型原始回答、处理后答案和错误信息。
- 题目满分、所得分、是否正确、是否跳过。
- 使用 Judge 时保存 Judge Prompt、Judge 原始回答、解析得分和 Judge 错误。

输出文件采用 UTF-8、`ensure_ascii=false` 和缩进格式，方便人工查看。

## Logging and Background Execution

进度日志格式保持单行、可搜索：

```text
[2026-08-03 10:20:30] INFO opseval_gen_0_shot 10/1651 success=9 failed=1
```

后台运行示例：

```bash
cd mini_demo
./run.sh start --tasks opseval_gen_0_shot --concurrency 6
./run.sh status
./run.sh logs
./run.sh stop
```

`start` 创建唯一 task ID 和运行目录；`status` 读取 PID 并检查进程；`logs` 使用 `tail -f`；`stop` 只停止 PID 文件对应的进程。重复 `start` 不覆盖已有运行目录。

## Error Handling

- 缺少推理模型环境变量时，在发送请求前直接报错退出。
- 任务名非法或数据文件缺失时直接报错，不静默跳过整个任务。
- 无法解析的源数据行或文件记录警告并跳过，其余有效样本继续运行。
- 某个任务完成后立即写出该任务 JSON；其他任务失败时已完成结果仍保留。
- 写 JSON 时先写同目录临时文件，再原子替换目标文件，避免生成半截 JSON。

## Testing and Acceptance

测试使用 `python -m unittest`，不引入第三方测试依赖。覆盖：

- URL 规范化和 OpenAI 响应解析。
- 网络请求首次失败、第二次成功时的重试次数。
- 连续三次失败时的错误结果。
- OpsEval、TeleExam 和 Exam 的最小样例加载。
- 单选、多选和带解释回答的选项提取。
- Exam 填空题快速匹配、选择题部分得分和总体加权百分比。
- Judge 数字解析、越界裁剪和失败样本排除。
- 输出配置中不包含 API Key。

验收命令：

```bash
python -m unittest discover -s mini_demo/tests -v
python mini_demo/mini_eval.py --tasks opseval_gen_0_shot --limit 2 --concurrency 1
```

验收成功标准：测试全部通过；冒烟运行生成合法 JSON；日志显示逐条进度；结果中保留推理原文和评分详情；任何文件和日志均不出现 API Key。
