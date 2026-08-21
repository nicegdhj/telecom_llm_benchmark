# Mini Demo 测评脚本

这是一个独立于 `ais_bench` 的轻量测评工具，仅使用 Python 标准库，支持：

- `opseval_gen_0_shot`
- `tele_exam_gen_0_shot`
- `tele_exam_gen_0_shot_str`
- `exam_gen_0_shot`

脚本通过 OpenAI 兼容的 `/chat/completions` HTTP 接口进行并发推理。每个请求失败后最多重试两次，即最多请求三次。

## 环境要求

- Python 3.10+
- 数据目录保持在仓库现有的 `data/` 下
- 无第三方 Python 依赖

## 模型配置

复制本地配置模板并填写密钥。`config.env` 已被 Git 忽略，`run.sh` 会自动加载；调用前已经导出的同名环境变量优先：

```bash
cp mini_demo/config.env.example mini_demo/config.env
chmod 600 mini_demo/config.env
```

默认 `INFER_API_KEY` 和 `INFER_BASE_URL` 可供多个模型共用。模型名会转换为大写下划线前缀，完整的模型级配置会覆盖默认值。例如 `deepseek-v4-flash` 使用：

```bash
export DEEPSEEK_V4_FLASH_INFER_API_KEY='<DeepSeek inference API key>'
export DEEPSEEK_V4_FLASH_INFER_BASE_URL='https://api.deepseek.com/chat/completions'
```

`INFER_BASE_URL` 可以是 `/v1` 基础地址，也可以是完整的 `/chat/completions` 地址。`INFER_MODEL` 用于兼容单模型运行；多模型轮测时通过 `--models` 指定，模型名会原样发送给接口。

主观题和 Exam 必须固定使用独立 LLM Judge：

```bash
export JUDGE_API_KEY='<judge-api-key>'
export JUDGE_BASE_URL='https://judge.example.com/v1'
export JUDGE_MODEL='judge-model-name'
```

选择 `tele_exam_gen_0_shot_str` 或 `exam_gen_0_shot` 时，三个 `JUDGE_*` 变量必须全部设置，不会继承当前推理模型。

## 前台运行

默认执行全部四个任务：

```bash
python3 mini_demo/mini_eval.py
```

只执行指定任务：

```bash
python3 mini_demo/mini_eval.py \
  --tasks opseval_gen_0_shot tele_exam_gen_0_shot \
  --concurrency 6
```

多个模型依次轮测全部任务：

```bash
python3 mini_demo/mini_eval.py \
  --models deepseek-v4-flash kimi-k3 GLM-5.2 \
  --concurrency 6
```

执行顺序是当前模型完成全部任务后再执行下一个模型；不同模型不会同时请求。

首次运行建议只测试两条数据：

```bash
python3 mini_demo/mini_eval.py \
  --tasks opseval_gen_0_shot \
  --limit 2 \
  --concurrency 1
```

常用参数：

| 参数 | 默认值 | 说明 |
| --- | --- | --- |
| `--models` | `INFER_MODEL` | 按顺序轮测的模型列表 |
| `--tasks` | 全部四项 | 要执行的一个或多个任务 |
| `--concurrency` | `6` | 推理并发数 |
| `--judge-concurrency` | 推理并发数 | LLM Judge 并发数 |
| `--max-tokens` | `2048` | 推理最大输出 token |
| `--judge-max-tokens` | `8192` | Judge 最大输出 token |
| `--timeout` | `120` | 单次 HTTP 请求超时秒数 |
| `--limit` | 不限制 | 每个任务只执行前 N 条，适合冒烟测试 |
| `--output-dir` | `mini_demo/outputs` | 输出根目录 |

## 后台运行

首次使用先赋予执行权限：

```bash
chmod +x mini_demo/run.sh
```

启动、查看状态、跟踪日志和停止：

```bash
mini_demo/run.sh start \
  --models deepseek-v4-flash Kimi-K3 GLM-5.2 \
  --tasks opseval_gen_0_shot \
  --concurrency 6
mini_demo/run.sh status
mini_demo/run.sh logs
mini_demo/run.sh stop
```

进度日志示例：

```text
[2026-08-03 10:20:30] INFO model=deepseek-v4-flash task=opseval_gen_0_shot 10/1651 success=9 failed=1
```

## 输出文件

每次运行创建独立目录：

```text
mini_demo/outputs/mini_eval_YYYYMMDD_HHMMSS_microseconds/
├── run.log
├── run_config.json
├── summary.json
├── deepseek-v4-flash/
│   ├── summary.json
│   └── <任务结果>.json
├── kimi-k3/
│   └── ...
└── GLM-5.2/
    └── ...
```

任务 JSON 中保存题目、Prompt、标准答案、模型回答、重建后的流式响应、处理后答案、请求次数、错误信息和评分详情。流式响应会保留 `content`、`reasoning_content`、`finish_reason` 和 `usage`。

每条成功推理包含性能指标：

- `ttft_seconds`：首个回答或思考 Token 延时。
- `first_answer_token_seconds`：首个正式答案 Token 延时。
- `total_latency_seconds`：总请求耗时。
- `tokens_per_second`：接口返回 `completion_tokens` 时计算。
- `chars_per_second`：接口不返回 token 用量时仍可使用的降级吞吐指标。

每个任务汇总上述指标的平均值、P50 和 P95。Judge 请求保持非流式，不参与性能统计。

`run_config.json` 不保存 API Key。选择题输出准确率；主观题输出 Judge 加权得分百分比；Exam 按题目分值和试卷汇总总体百分比。推理或 Judge 最终失败的样本会保留错误并从有效评分分母中排除。

## 测试

```bash
python3 -m unittest discover -s mini_demo/tests -v
bash -n mini_demo/run.sh
```
