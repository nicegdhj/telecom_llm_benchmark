# Mini Evaluation Multi-Model and Performance Design

## Goal

扩展 `mini_demo`，支持一次配置多个推理模型，严格按照“当前模型完成全部任务后再执行下一个模型”的顺序轮测；每个模型使用独立结果目录。同时将推理请求改为 SSE 流式模式，采集首 Token 延时和生成吞吐等性能指标。

本扩展保持现有四个任务、评分逻辑、任务内并发、两次重试和后台运行方式不变。

## Model Configuration

命令行新增 `--models`：

```bash
python3 mini_demo/mini_eval.py \
  --models deepseek-v4-flash kimi-k3 GLM-5.2 \
  --tasks opseval_gen_0_shot tele_exam_gen_0_shot
```

规则：

- 模型名按命令行原样传给接口，不修改大小写。
- 所有被测模型共用 `INFER_API_KEY` 和 `INFER_BASE_URL`。
- `--models` 未提供时，兼容读取单模型环境变量 `INFER_MODEL`。
- 同时提供 `--models` 和 `INFER_MODEL` 时，以 `--models` 为准。
- 模型列表不能为空，重复模型在启动时直接报错。

Judge 固定使用独立配置：

- `JUDGE_API_KEY`
- `JUDGE_BASE_URL`
- `JUDGE_MODEL`

当所选任务包含 `tele_exam_gen_0_shot_str` 或 `exam_gen_0_shot` 时，三个 Judge 变量必须全部配置，且不会继承任何当前推理模型配置。Judge 客户端在整次运行中只创建一次并被所有模型复用。

## Execution Order

执行顺序为：

```text
model 1
  task 1
  task 2
  task 3
  task 4
model 2
  task 1
  task 2
  task 3
  task 4
...
```

- 模型之间串行，避免不同模型的请求混在一起。
- 每个任务内部继续使用 `--concurrency` 控制样本并发。
- Judge 使用固定的 `--judge-concurrency`。
- 单条推理失败仍保留错误并继续当前任务。
- 配置、数据缺失或未处理的任务级错误仍终止整次运行，避免生成不完整但看似成功的对比结果。

## Output Layout

每次运行创建一个总目录，每个模型创建独立子目录：

```text
mini_demo/outputs/<run_id>/
├── run.log
├── run_config.json
├── summary.json
├── deepseek-v4-flash/
│   ├── summary.json
│   ├── opseval_gen_0_shot.json
│   ├── tele_exam_gen_0_shot.json
│   ├── tele_exam_gen_0_shot_str.json
│   └── exam_gen_0_shot.json
├── kimi-k3/
│   └── ...
└── GLM-5.2/
    └── ...
```

模型目录名由模型名安全化得到：仅保留字母、数字、`.`、`_`、`-`，其他字符替换为 `_`。如果两个模型名安全化后目录名冲突，则启动前报错，不覆盖结果。

顶层 `summary.json` 按输入顺序保存全部模型的任务指标，便于横向比较。模型目录内的 `summary.json` 只保存该模型的任务指标。

## Streaming Inference

推理客户端新增流式方法，向 Chat Completions 接口发送：

```json
{
  "model": "current-model",
  "messages": [{"role": "user", "content": "rendered prompt"}],
  "stream": true,
  "stream_options": {"include_usage": true},
  "max_tokens": 2048,
  "temperature": 0
}
```

客户端逐行解析 OpenAI 兼容 SSE：

- 忽略空行和注释行。
- 解析 `data: {...}`。
- 遇到 `data: [DONE]` 结束。
- 顺序拼接 `choices[0].delta.content`。
- 顺序拼接 `choices[0].delta.reasoning_content`。
- 保存最后出现的 `finish_reason`。
- 保存任意分片中出现的 `usage`。

如果接口在 `stream=true` 下返回普通 JSON，客户端按非流式响应兼容解析，但该响应无法得到真实 TTFT，`ttft_seconds` 记为 `null`。

如果接口以 HTTP 400/422 明确拒绝 `stream_options`，客户端在同一次尝试内移除 `stream_options` 后重新发送，并为该模型后续请求关闭此字段。该能力状态使用锁保护，避免任务并发时发生数据竞争；此时若流中没有 `usage`，按已确认规则将 `tokens_per_second` 设为 `null`，继续提供 `chars_per_second`。

每次失败后最多额外重试两次。性能指标只统计最终成功的那次尝试，不把失败等待时间混入成功指标。最终失败时保留最后一次可读取的响应信息。

Judge 请求继续使用 `stream=false`，不采集性能指标，避免影响评分逻辑。

## Performance Metrics

每条成功推理样本新增 `performance`：

```json
{
  "ttft_seconds": 0.4321,
  "first_answer_token_seconds": 0.8123,
  "total_latency_seconds": 3.2456,
  "generation_seconds": 2.8135,
  "completion_tokens": 128,
  "tokens_per_second": 45.5,
  "output_chars": 356,
  "chars_per_second": 126.53
}
```

定义：

- `ttft_seconds`：请求开始到首个非空 `reasoning_content` 或 `content` 增量的时间。
- `first_answer_token_seconds`：请求开始到首个非空 `content` 增量的时间；纯答案模型通常与 TTFT 相同，推理模型可能更晚。
- `total_latency_seconds`：请求开始到流结束的总时间。
- `generation_seconds`：`total_latency_seconds - ttft_seconds`。
- `completion_tokens`：接口 `usage.completion_tokens`；接口不返回时为 `null`。
- `tokens_per_second`：`completion_tokens / generation_seconds`；缺少 token 数或生成时间为零时为 `null`。
- `output_chars`：最终 `content` 与 `reasoning_content` 的字符总数。
- `chars_per_second`：`output_chars / generation_seconds`；作为 token 用量缺失时的明确降级指标。

计时使用 `time.perf_counter()`。所有秒数和吞吐保留四位小数。

失败样本的 `performance` 保留已知时间，无法确定的指标为 `null`，且不参与性能汇总。

## Performance Aggregation

每个任务的 `metrics` 增加 `performance` 汇总，只统计成功且对应指标非空的样本：

```json
{
  "successful_samples": 248,
  "ttft_seconds": {"mean": 0.51, "p50": 0.47, "p95": 0.92},
  "tokens_per_second": {"mean": 42.1, "p50": 41.3, "p95": 55.8},
  "chars_per_second": {"mean": 118.2, "p50": 115.0, "p95": 160.3}
}
```

百分位使用排序后的线性插值，不引入第三方统计库。无有效数据的指标为：

```json
{"mean": null, "p50": null, "p95": null}
```

顶层模型汇总保留每个任务的性能指标，不额外将不同任务混合成一个总体吞吐，避免不同输出长度和题型造成误导。

## Stored Streaming Response

流式接口不存在单个原始 JSON 响应。为避免保存每个 Token 分片导致结果文件大幅膨胀，`raw_response` 保存重建后的结构：

```json
{
  "stream": true,
  "content": "final visible answer",
  "reasoning_content": "reconstructed reasoning",
  "finish_reason": "stop",
  "usage": {"completion_tokens": 128}
}
```

不保存完整 SSE chunk 列表。接口返回的 API Key 或 Authorization 内容仍需递归脱敏。

## Logging

日志在现有任务进度前增加模型名：

```text
[2026-08-03 18:00:00] INFO model=deepseek-v4-flash task=opseval_gen_0_shot 10/1651 success=9 failed=1
```

模型开始和完成时分别记录：

```text
INFO model=deepseek-v4-flash started 1/3
INFO model=deepseek-v4-flash completed 1/3
```

后台 `run.sh start/status/logs/stop` 行为不变。

## Testing

在现有标准库 `unittest` 基础上增加：

- `--models` 优先级、重复模型和空模型校验。
- 模型目录安全化与冲突检测。
- 两个模型严格串行、每个模型执行全部任务的调用顺序。
- SSE `content`、`reasoning_content`、`finish_reason` 和 `[DONE]` 解析。
- 首 Token、首答案 Token、总延时和生成时长计算。
- `usage.completion_tokens` 存在时的 `tokens/s`。
- usage 缺失时 `tokens/s=null`、`chars/s` 可用。
- 流式失败重试后只使用成功尝试的性能数据。
- 普通 JSON 响应兼容与 `ttft_seconds=null`。
- 固定 Judge 配置缺失时的失败行为，以及不同推理模型复用同一 Judge。
- 每模型独立目录、模型级 summary 和顶层 summary。

验收仍不自动调用付费接口。使用假 SSE 响应完成自动测试，再提供真实接口双模型小样本命令：

```bash
python3 mini_demo/mini_eval.py \
  --models deepseek-v4-flash kimi-k3 \
  --tasks opseval_gen_0_shot \
  --limit 2 \
  --concurrency 1
```
