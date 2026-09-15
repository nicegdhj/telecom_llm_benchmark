# Mini Evaluation Multi-Model Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add sequential multi-model evaluation, per-model output directories, fixed Judge configuration, and streaming inference performance metrics.

**Architecture:** Extend `ChatClient` with an SSE streaming method while preserving non-streaming Judge requests. Keep model iteration in `mini_eval.py` outside the existing task loop, and add pure helpers for model resolution, directory safety, and performance aggregation.

**Tech Stack:** Python 3.10 standard library, OpenAI-compatible SSE, POSIX shell, `unittest`.

**Constraint:** Do not commit unless the user explicitly requests it.

---

### Task 1: Streaming HTTP Metrics

**Files:**
- Modify: `mini_demo/http_client.py`
- Modify: `mini_demo/tests/test_mini_eval.py`

- [ ] Write failing tests using fake SSE responses for content/reasoning reconstruction, TTFT, first answer latency, usage, throughput, missing-usage fallback, and ordinary JSON fallback.
- [ ] Run `python3 -m unittest mini_demo.tests.test_mini_eval.StreamingHttpClientTests -v` and verify failures are caused by missing streaming behavior.
- [ ] Add performance fields to `ChatResult` and implement `ChatClient.complete_stream()` with `time.perf_counter()`, SSE parsing, two retries, recursive response sanitization, and reconstructed raw response.
- [ ] Handle explicit HTTP 400/422 rejection of `stream_options` by disabling it under a lock and retrying the same attempt without counting an additional fault-tolerance retry.
- [ ] Re-run the streaming tests and verify GREEN.

### Task 2: Performance Aggregation

**Files:**
- Modify: `mini_demo/mini_eval.py`
- Modify: `mini_demo/tests/test_mini_eval.py`

- [ ] Write failing tests for mean/P50/P95, null metrics, and inference rows retaining per-sample performance.
- [ ] Add `summarize_performance()` using linear percentile interpolation and four-decimal rounding.
- [ ] Change `infer_samples()` to call `complete_stream()` and include a `performance` object in each row.
- [ ] Merge performance aggregation into every task's existing score metrics without changing score denominators.
- [ ] Run focused runner tests and verify GREEN.

### Task 3: Multi-Model Sequential Runner

**Files:**
- Modify: `mini_demo/mini_eval.py`
- Modify: `mini_demo/tests/test_mini_eval.py`

- [ ] Write failing tests for `--models` precedence, duplicate rejection, safe directory names, directory collisions, and exact model/task call order.
- [ ] Add `--models`, retain `INFER_MODEL` fallback, and validate model names before creating output directories.
- [ ] Add `safe_model_directory()` that replaces characters outside `[A-Za-z0-9._-]` with `_` and rejects collisions.
- [ ] Move the task loop inside a model loop; create one inference client per model and one fixed Judge client per run.
- [ ] Write task files and model `summary.json` under `<run>/<model-dir>/`; write ordered cross-model metrics to top-level `summary.json`.
- [ ] Prefix progress logs with `model=<name> task=<task>`.
- [ ] Run multi-model runner tests and verify GREEN.

### Task 4: Fixed Judge Configuration

**Files:**
- Modify: `mini_demo/mini_eval.py`
- Modify: `mini_demo/tests/test_mini_eval.py`

- [ ] Write failing tests showing subjective/Exam task selection requires all three `JUDGE_*` values and choice-only tasks do not.
- [ ] Remove Judge fallback inheritance and instantiate the fixed Judge once outside the model loop.
- [ ] Keep Judge requests non-streaming and reuse the same client object for all models.
- [ ] Verify existing Judge score tests still pass.

### Task 5: Documentation and Full Verification

**Files:**
- Modify: `mini_demo/README.md`
- Verify: `mini_demo/run.sh`

- [ ] Document `--models`, fixed Judge requirements, model directory layout, TTFT, first answer latency, throughput definitions, and usage fallback.
- [ ] Run `python3 -m unittest discover -s mini_demo/tests -v`.
- [ ] Run Python 3.10 grammar, `py_compile`, `bash -n`, `git diff --check`, credential scan, and a fake-SSE two-model offline smoke test.
- [ ] Request independent code review and fix every Critical or Important finding.
- [ ] Report a real endpoint smoke command without automatically consuming the user's API quota.
