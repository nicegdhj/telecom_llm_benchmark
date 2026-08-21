# Mini Evaluation Runner Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Python 3.10+ runner for four existing evaluation tasks with concurrent OpenAI-compatible HTTP inference, two retries, JSON outputs, compatible scoring, and background process management.

**Architecture:** Keep transport, task behavior, and orchestration separate. `http_client.py` owns URL normalization and reliable requests; `task_logic.py` owns loading, prompts, answer parsing, and scoring; `mini_eval.py` owns concurrency, progress, output directories, and CLI behavior. The implementation uses only the Python standard library.

**Tech Stack:** Python 3.10+ standard library (`argparse`, `concurrent.futures`, `dataclasses`, `json`, `logging`, `pathlib`, `urllib`), POSIX shell, `unittest`.

**Constraint:** Do not commit changes unless the user explicitly asks for a commit.

---

## File Map

- Create `mini_demo/http_client.py`: OpenAI-compatible HTTP client, URL normalization, response parsing, timeout, retry, and safe error text.
- Create `mini_demo/task_logic.py`: sample model, four dataset loaders, prompts, option extraction, judge score parsing, and per-task score aggregation.
- Create `mini_demo/mini_eval.py`: CLI, environment configuration, inference and judge thread pools, progress logging, atomic JSON output, and run summary.
- Create `mini_demo/run.sh`: `start`, `status`, `logs`, and `stop` commands using `nohup` and PID files.
- Create `mini_demo/README.md`: setup, security guidance, foreground/background examples, task names, and output schema.
- Create `mini_demo/tests/__init__.py`: test package marker.
- Create `mini_demo/tests/test_mini_eval.py`: standard-library tests for transport, loaders, evaluators, output sanitization, and orchestration helpers.
- Preserve `mini_demo/__init__.py`: existing package marker.

### Task 1: Reliable HTTP Client

**Files:**
- Create: `mini_demo/http_client.py`
- Create: `mini_demo/tests/__init__.py`
- Create: `mini_demo/tests/test_mini_eval.py`

- [ ] **Step 1: Write failing URL and retry tests**

Add tests that define the required public API:

```python
from mini_demo.http_client import ChatClient, normalize_chat_url


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


class HttpClientTests(unittest.TestCase):
    def test_normalize_chat_url_accepts_base_and_full_urls(self):
        self.assertEqual(
            normalize_chat_url("https://example.test/v1"),
            "https://example.test/v1/chat/completions",
        )
        self.assertEqual(
            normalize_chat_url("https://example.test/v1/chat/completions"),
            "https://example.test/v1/chat/completions",
        )

    def test_complete_retries_twice_then_succeeds(self):
        attempts = []

        def opener(_request, timeout):
            attempts.append(timeout)
            if len(attempts) < 3:
                raise OSError("temporary failure")
            return FakeResponse({"choices": [{"message": {"content": "A"}}]})

        client = ChatClient(
            api_key="secret",
            base_url="https://example.test/v1",
            model="test-model",
            timeout=9,
            opener=opener,
            sleeper=lambda _seconds: None,
        )
        result = client.complete("question", max_tokens=32)
        self.assertEqual(result.content, "A")
        self.assertEqual(result.attempts, 3)
        self.assertEqual(len(attempts), 3)

    def test_complete_returns_failure_after_three_attempts(self):
        def opener(_request, timeout):
            raise OSError("network unavailable")

        client = ChatClient(
            api_key="secret",
            base_url="https://example.test/v1",
            model="test-model",
            opener=opener,
            sleeper=lambda _seconds: None,
        )
        result = client.complete("question", max_tokens=32)
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.attempts, 3)
        self.assertNotIn("secret", result.error)
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.HttpClientTests -v
```

Expected: import failure because `mini_demo.http_client` does not exist.

- [ ] **Step 3: Implement the minimal HTTP client**

Implement these interfaces in `mini_demo/http_client.py`:

```python
@dataclass
class ChatResult:
    status: str
    content: str
    attempts: int
    error: str = ""


def normalize_chat_url(base_url: str) -> str:
    url = base_url.strip().rstrip("/")
    if not url:
        raise ValueError("base URL must not be empty")
    if url.endswith("/chat/completions"):
        return url
    return f"{url}/chat/completions"


class ChatClient:
    def __init__(self, api_key, base_url, model, timeout=120,
                 retries=2, opener=None, sleeper=None):
        self.api_key = api_key
        self.url = normalize_chat_url(base_url)
        self.model = model
        self.timeout = timeout
        self.retries = retries
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleeper or time.sleep

    def complete(self, prompt, max_tokens, temperature=0.0):
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        for attempt in range(1, self.retries + 2):
            try:
                request = urllib.request.Request(
                    self.url,
                    data=json.dumps(payload).encode("utf-8"),
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {self.api_key}",
                    },
                    method="POST",
                )
                with self._opener(request, timeout=self.timeout) as response:
                    data = json.loads(response.read().decode("utf-8"))
                content = data["choices"][0]["message"]["content"]
                if not isinstance(content, str) or not content.strip():
                    raise ValueError("empty choices[0].message.content")
                return ChatResult("success", content, attempt)
            except Exception as exc:
                if attempt > self.retries:
                    return ChatResult("failed", "", attempt, _safe_error(exc))
                self._sleep(attempt)
```

`_safe_error()` must return only exception type and message, remove the API key if an upstream exception unexpectedly contains it, and never include request headers.

- [ ] **Step 4: Run HTTP client tests and verify GREEN**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.HttpClientTests -v
```

Expected: all `HttpClientTests` pass.

### Task 2: Dataset Loading and Prompt Compatibility

**Files:**
- Create: `mini_demo/task_logic.py`
- Modify: `mini_demo/tests/test_mini_eval.py`

- [ ] **Step 1: Write failing loader and prompt tests**

Use `tempfile.TemporaryDirectory()` to create one minimal fixture for each source format. Define the expected sample API:

```python
from mini_demo.task_logic import EvalSample, load_task


class TaskLoadingTests(unittest.TestCase):
    def test_load_opseval_normalizes_answer_and_prompt(self):
        root = self.make_root()
        self.write_jsonl(
            root / "data/OpsEval/5G_Communication.jsonl",
            [{"id": "1", "question": "Q\nA:x\nB:y", "answer": "B, "}],
        )
        self.write_empty_opseval_subsets(root)
        samples = load_task("opseval_gen_0_shot", root)
        self.assertEqual(samples[0].answer, "B")
        self.assertIn("Please select the correct answer", samples[0].prompt)

    def test_load_tele_choice_uses_2023_comprehensive_only(self):
        root = self.make_root()
        self.write_json(
            root / "data/telecom-intermediate-exam/2023/综合/paper.json",
            [{"id": "1", "question": "Q", "answer": "A",
              "correct answer": "C"}],
        )
        samples = load_task("tele_exam_gen_0_shot", root)
        self.assertEqual(samples[0].answer, "C")
        self.assertEqual(samples[0].subdivision, "paper")

    def test_load_tele_subjective_keeps_score_and_normalizes_symbol(self):
        root = self.make_root()
        self.write_json(
            root / "data/telecom-intermediate-exam/2023/互联网技术/paper.json",
            [{"id": "1", "question": "Q", "answer": "√", "score": "3分"}],
        )
        samples = load_task("tele_exam_gen_0_shot_str", root)
        self.assertEqual(samples[0].answer, "正确")
        self.assertEqual(samples[0].max_score, 3.0)

    def test_load_exam_adds_type_specific_prompt_and_skips_images(self):
        root = self.make_root()
        self.write_json(
            root / "data/exam/exam_858_2022.json",
            {
                "fill_blank": [
                    {"id": "1", "question": "Q", "answer": "x", "score": "2"},
                    {"id": "2", "question": "image", "answer": "y",
                     "has_image": True},
                ]
            },
        )
        samples = load_task("exam_gen_0_shot", root)
        self.assertEqual(len(samples), 1)
        self.assertEqual(samples[0].question_type, "fill_blank")
        self.assertIn("不要包含解题过程", samples[0].prompt)
```

- [ ] **Step 2: Run loader tests and verify RED**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.TaskLoadingTests -v
```

Expected: import failure because `mini_demo.task_logic` does not exist.

- [ ] **Step 3: Implement the sample model and loaders**

Create a single transport-neutral sample type:

```python
@dataclass
class EvalSample:
    sample_id: str
    task: str
    subdivision: str
    question_type: str
    question: str
    prompt: str
    answer: str
    max_score: float = 1.0
```

Implement:

```python
SUPPORTED_TASKS = (
    "opseval_gen_0_shot",
    "tele_exam_gen_0_shot",
    "tele_exam_gen_0_shot_str",
    "exam_gen_0_shot",
)


def load_task(task_name: str, root: Path, limit: int | None = None) -> list[EvalSample]:
    loaders = {
        "opseval_gen_0_shot": _load_opseval,
        "tele_exam_gen_0_shot": _load_tele_choice,
        "tele_exam_gen_0_shot_str": _load_tele_subjective,
        "exam_gen_0_shot": _load_exam,
    }
    if task_name not in loaders:
        raise ValueError(f"unsupported task: {task_name}")
    samples = loaders[task_name](root)
    if not samples:
        raise ValueError(f"no samples loaded for task: {task_name}")
    return samples if limit is None else samples[:limit]
```

Use the exact file lists and prompt text recorded in the design specification. Loader requirements:

- Raise `FileNotFoundError` for a required missing directory or configured file.
- Preserve stable sorted file and row order.
- Parse score strings using the first numeric token and default to `1.0`.
- Normalize Exam dictionary answers by numeric key order.
- Ignore unsupported Exam top-level keys, matching the existing evaluator.

- [ ] **Step 4: Run loader tests and verify GREEN**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.TaskLoadingTests -v
```

Expected: all loader tests pass.

### Task 3: Compatible Scoring Logic

**Files:**
- Modify: `mini_demo/task_logic.py`
- Modify: `mini_demo/tests/test_mini_eval.py`

- [ ] **Step 1: Write failing option, Judge, and Exam scoring tests**

Add focused tests:

```python
from mini_demo.task_logic import (
    extract_first_option,
    extract_exam_choices,
    normalize_latex,
    parse_judge_score,
    summarize_choice_results,
    summarize_exam_results,
)


class ScoringTests(unittest.TestCase):
    def test_extract_first_option_prefers_explicit_answer(self):
        self.assertEqual(extract_first_option("分析中提到 A。\n最终答案：C", "ABCD"), "C")

    def test_exam_choice_scoring_supports_multiple_blanks(self):
        self.assertEqual(extract_exam_choices("答案：AC", 2), "AC")

    def test_latex_normalization_ignores_display_only_differences(self):
        self.assertEqual(normalize_latex(r"$\dfrac{1}{2}$"), normalize_latex(r"\frac{1}{2}"))

    def test_parse_judge_score_supports_json_and_clamps(self):
        self.assertEqual(parse_judge_score('{"score": 7}', 5.0), 5.0)
        self.assertEqual(parse_judge_score("reason\n3", 5.0), 3.0)

    def test_choice_accuracy_excludes_failed_inference(self):
        results = [
            {"status": "success", "processed_answer": "A", "answer": "A"},
            {"status": "success", "processed_answer": "B", "answer": "A"},
            {"status": "failed", "processed_answer": "", "answer": "A"},
        ]
        self.assertEqual(summarize_choice_results(results)["accuracy"], 50.0)

    def test_exam_summary_uses_global_weighted_percentage(self):
        details = [
            {"subdivision": "p1", "got_score": 1.0, "max_score": 2.0,
             "skipped": False},
            {"subdivision": "p2", "got_score": 8.0, "max_score": 8.0,
             "skipped": False},
        ]
        summary = summarize_exam_results(details)
        self.assertEqual(summary["overall_score_percentage"], 90.0)
```

- [ ] **Step 2: Run scoring tests and verify RED**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.ScoringTests -v
```

Expected: missing scoring functions.

- [ ] **Step 3: Implement deterministic scoring helpers**

Implement the existing evaluator behavior as pure functions:

```python
def extract_first_option(text: str, options: str) -> str:
    explicit_patterns = (
        rf"(?:最终|正确|标准)?答案\s*[:：为是选]*\s*[（(]?([{options}])",
        rf"(?i:answer)\s*(?:is)?\s*[:：]?\s*[（(]?([{options}])",
        rf"\\boxed\s*\{{\s*(?:\\text\s*\{{)?([{options}])",
    )
    for pattern in explicit_patterns:
        matches = re.findall(pattern, text)
        if matches:
            return matches[-1].upper()
    match = re.search(rf"[{options}]", text.upper())
    return match.group(0) if match else ""


def parse_judge_score(output: str, max_score: float) -> float | None:
    if not output or not output.strip():
        return None
    clean = re.sub(r"<think>.*?</think>", "", output, flags=re.DOTALL)
    score_match = re.search(
        r'["\']score["\']\s*:\s*["\']?([\d.]+)', clean, re.IGNORECASE
    )
    if score_match:
        value = float(score_match.group(1))
    else:
        standalone = re.findall(r"^\s*([\d.]+)\s*$", clean, re.MULTILINE)
        numbers = standalone or re.findall(r"([\d.]+)", clean)
        if not numbers:
            return 0.0
        value = float(numbers[-1])
    return min(max(value, 0.0), max_score)
```

Also implement:

- `extract_exam_choices(text, expected_len)` with Chinese answer prefix, English answer prefix, exact-length uppercase groups, then uppercase-letter fallback.
- `normalize_latex(text)` with outer dollar removal, `dfrac/tfrac` conversion, `left/right` removal, display-style removal, math-spacing removal, and whitespace folding.
- `score_exam_choice(prediction, reference)` returning positional match ratio.
- `summarize_choice_results(details)` returning `accuracy`, `correct`, `evaluated`, and `failed`.
- `summarize_exam_results(details)` returning each paper percentage and globally weighted `overall_score_percentage`, excluding `skipped` or `got_score is None` rows.

- [ ] **Step 4: Implement Judge prompt construction**

Add `build_judge_prompt(prediction, reference, max_score)` using the current generic evaluator wording and requiring a numeric score at the end. Keep the prompt local to `task_logic.py`; do not import ais_bench.

- [ ] **Step 5: Run scoring tests and verify GREEN**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.ScoringTests -v
```

Expected: all scoring tests pass.

### Task 4: Concurrent Runner and JSON Outputs

**Files:**
- Create: `mini_demo/mini_eval.py`
- Modify: `mini_demo/tests/test_mini_eval.py`

- [ ] **Step 1: Write failing runner helper tests**

Define dependency-injected orchestration helpers so tests do not use the network:

```python
from mini_demo.mini_eval import (
    ModelSettings,
    atomic_write_json,
    infer_samples,
    public_run_config,
)


class RunnerTests(unittest.TestCase):
    def test_public_run_config_does_not_expose_keys(self):
        infer = ModelSettings("secret-a", "https://a/v1", "model-a")
        judge = ModelSettings("secret-b", "https://b/v1", "model-b")
        config = public_run_config(infer, judge, {"concurrency": 2})
        rendered = json.dumps(config)
        self.assertNotIn("secret-a", rendered)
        self.assertNotIn("secret-b", rendered)
        self.assertEqual(config["infer_model"], "model-a")

    def test_infer_samples_preserves_input_order(self):
        samples = [self.sample("1"), self.sample("2")]

        class Client:
            def complete(self, prompt, max_tokens, temperature=0.0):
                return ChatResult("success", f"answer-{prompt}", 1)

        rows = infer_samples(samples, Client(), concurrency=2, max_tokens=8)
        self.assertEqual([row["sample_id"] for row in rows], ["1", "2"])

    def test_atomic_write_json_creates_valid_utf8_json(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "result.json"
            atomic_write_json(path, {"answer": "正确"})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["answer"], "正确")
```

- [ ] **Step 2: Run runner tests and verify RED**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.RunnerTests -v
```

Expected: import failure because `mini_demo.mini_eval` does not exist.

- [ ] **Step 3: Implement model settings and inference concurrency**

Implement:

```python
@dataclass(frozen=True)
class ModelSettings:
    api_key: str
    base_url: str
    model: str


def infer_samples(samples, client, concurrency, max_tokens, progress=None):
    rows = [None] * len(samples)
    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {
            executor.submit(client.complete, sample.prompt, max_tokens): index
            for index, sample in enumerate(samples)
        }
        completed = success = failed = 0
        for future in as_completed(futures):
            index = futures[future]
            result = future.result()
            rows[index] = _inference_row(samples[index], result)
            completed += 1
            success += result.status == "success"
            failed += result.status != "success"
            if progress:
                progress(completed, len(samples), success, failed)
    return rows
```

`_inference_row()` must retain sample metadata, prompt, raw answer, attempts, status, and error. It must not retain headers or keys.

- [ ] **Step 4: Implement Judge concurrency and task evaluation**

Add a second thread-pool helper that receives only rows requiring LLM Judge, calls `build_judge_prompt()`, stores Judge prompt/raw output/attempts/error, parses the score, and merges the results back in original order.

Evaluation routing must be exact:

- OpsEval and TeleExam choice: postprocess successful raw responses and compute choice accuracy.
- TeleExam subjective: Judge every successful inference; use each sample's `max_score`; exclude failed inference or Judge rows from valid score denominator.
- Exam multiple choice: positional partial credit.
- Exam fill blank: exact, no-space, and normalized-LaTeX fast paths; Judge only unmatched rows.
- Exam subjective: Judge every successful non-skipped row.

- [ ] **Step 5: Implement CLI and output lifecycle**

Create `argparse` options from the approved design. Resolve repository root from `Path(__file__).resolve().parents[1]`. Validate positive concurrency, token, timeout, and limit values before loading data.

Run lifecycle:

```python
task_id = datetime.now().strftime("mini_eval_%Y%m%d_%H%M%S")
run_dir = output_root / task_id
run_dir.mkdir(parents=True, exist_ok=False)
atomic_write_json(run_dir / "run_config.json", safe_config)
for task_name in args.tasks:
    samples = load_task(task_name, repo_root, args.limit)
    inference_rows = infer_samples(...)
    metrics, evaluated_rows = evaluate_rows(...)
    atomic_write_json(run_dir / f"{task_name}.json", task_payload)
atomic_write_json(run_dir / "summary.json", summary)
```

Configure a logger with both stdout and `run.log` handlers. Progress callback format:

```python
logger.info(
    "%s %d/%d success=%d failed=%d",
    task_name, completed, total, success, failed,
)
```

Exit nonzero only for configuration errors, missing task data, or an unhandled task-level failure. Per-sample failures remain in JSON and do not stop the run.

- [ ] **Step 6: Run runner tests and verify GREEN**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.RunnerTests -v
```

Expected: all runner tests pass.

### Task 5: Background Launcher and Usage Documentation

**Files:**
- Create: `mini_demo/run.sh`
- Create: `mini_demo/README.md`
- Modify: `mini_demo/tests/test_mini_eval.py`

- [ ] **Step 1: Write a failing launcher syntax/contract test**

Add a test that reads `run.sh` and asserts the four commands are present and the script never embeds API key values:

```python
class LauncherTests(unittest.TestCase):
    def test_launcher_exposes_required_commands(self):
        script = (REPO_ROOT / "mini_demo/run.sh").read_text(encoding="utf-8")
        for command in ("start", "status", "logs", "stop"):
            self.assertIn(command, script)
        self.assertNotIn("sk-", script)
```

- [ ] **Step 2: Run launcher test and verify RED**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.LauncherTests -v
```

Expected: failure because `run.sh` does not exist.

- [ ] **Step 3: Implement `run.sh`**

Use `#!/usr/bin/env bash` and `set -euo pipefail`. Resolve `SCRIPT_DIR`, store launcher metadata under `mini_demo/.runs`, and implement:

- `start`: require model environment variables, create a timestamped ID, launch `nohup python3 "$SCRIPT_DIR/mini_eval.py" --output-dir "$SCRIPT_DIR/outputs" "$@"`, redirect launcher output to a temporary start log, write PID and active task ID, then print PID and log location.
- `status`: read active PID, use `kill -0`, and print running/stopped state.
- `logs`: locate the newest run log and execute `tail -f`.
- `stop`: send `TERM` only to the recorded PID and remove the active PID file after the process exits.

Do not source a checked-in `.env` file and do not echo environment variable values.

- [ ] **Step 4: Write `README.md`**

Document safe setup without embedding the supplied key:

```bash
export INFER_API_KEY='<your-api-key>'
export INFER_BASE_URL='https://api.example.com/api/llm/v1'
export INFER_MODEL='your-model-name'
```

Document optional `JUDGE_API_KEY`, `JUDGE_BASE_URL`, and `JUDGE_MODEL`, all CLI flags, foreground execution, `run.sh start/status/logs/stop`, output paths, metrics, retry semantics, and a two-sample smoke command.

- [ ] **Step 5: Run launcher test and shell syntax check**

Run:

```bash
python -m unittest mini_demo.tests.test_mini_eval.LauncherTests -v
bash -n mini_demo/run.sh
```

Expected: test passes and `bash -n` exits zero.

### Task 6: Full Verification

**Files:**
- Verify all files under `mini_demo`

- [ ] **Step 1: Run the complete unit test suite**

Run:

```bash
python -m unittest discover -s mini_demo/tests -v
```

Expected: all tests pass without network access.

- [ ] **Step 2: Run static syntax checks**

Run:

```bash
python -m py_compile mini_demo/http_client.py mini_demo/task_logic.py mini_demo/mini_eval.py
bash -n mini_demo/run.sh
git diff --check -- mini_demo docs/superpowers/specs/2026-08-03-mini-evaluation-runner-design.md docs/superpowers/plans/2026-08-03-mini-evaluation-runner-implementation-plan.md
```

Expected: every command exits zero.

- [ ] **Step 3: Scan generated source for credential leakage**

Run:

```bash
rg -n "Authorization: Bearer [A-Za-z0-9]" mini_demo
```

Expected: no matches.

- [ ] **Step 4: Run an offline fake-client smoke test**

Use the unit-test fake client to load two real OpsEval samples, execute `infer_samples()` with concurrency `2`, score them, and write the result to a temporary directory. Verify the output parses as JSON and contains two samples.

- [ ] **Step 5: Report the live smoke-test command without exposing credentials**

Do not call the paid external endpoint automatically. Report this user-run command:

```bash
python mini_demo/mini_eval.py \
  --tasks opseval_gen_0_shot \
  --limit 2 \
  --concurrency 1
```

Expected when the user's environment variables are exported: a new output directory containing `run.log`, `run_config.json`, `opseval_gen_0_shot.json`, and `summary.json`.
