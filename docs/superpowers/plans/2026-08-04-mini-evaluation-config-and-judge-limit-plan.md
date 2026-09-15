# Mini Evaluation Config and Judge Limit Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Load one local environment file, resolve inference credentials per model, and default Judge output to 8192 tokens.

**Architecture:** Keep `config.env` loading in the shell launcher and credential selection in `mini_eval.py`. Default `INFER_*` values serve shared endpoints, while normalized model-specific variables override them only when both key and URL are present.

**Tech Stack:** Bash, Python 3.10 standard library, `unittest`.

---

### Task 1: Judge token default

**Files:**
- Modify: `mini_demo/tests/test_mini_eval.py`
- Modify: `mini_demo/mini_eval.py`

- [ ] Add a parser test asserting `judge_max_tokens == 8192` when omitted.
- [ ] Run the focused test and confirm it fails with `512 != 8192`.
- [ ] Change the parser default to 8192.
- [ ] Run the focused test and confirm it passes.

### Task 2: Per-model inference configuration

**Files:**
- Modify: `mini_demo/tests/test_mini_eval.py`
- Modify: `mini_demo/mini_eval.py`

- [ ] Add tests for default inference settings, normalized model overrides, and incomplete overrides.
- [ ] Run the focused tests and confirm the resolver is missing.
- [ ] Implement a small resolver that selects a complete model override or falls back to default settings.
- [ ] Use the resolver when constructing each model's `ChatClient` and safe run configuration.
- [ ] Run the focused tests and confirm they pass.

### Task 3: Local configuration file

**Files:**
- Modify: `mini_demo/.gitignore`
- Create: `mini_demo/config.env.example`
- Create locally: `mini_demo/config.env`
- Modify: `mini_demo/run.sh`
- Modify: `mini_demo/tests/test_mini_eval.py`
- Modify: `mini_demo/README.md`

- [ ] Add a shell test proving `run.sh` loads `config.env` while preserving already exported values.
- [ ] Run the shell test and confirm startup fails before configuration loading exists.
- [ ] Add automatic loading for `MINI_DEMO_CONFIG` or `mini_demo/config.env`.
- [ ] Ignore the real file, add a placeholder example, and write the local mode-600 configuration.
- [ ] Document one-file three-model execution and configuration precedence.
- [ ] Run the shell test and confirm it passes.

### Task 4: Verification and online smoke test

**Files:**
- Verify: `mini_demo/tests/test_mini_eval.py`
- Generate ignored outputs under: `mini_demo/outputs/`

- [ ] Run all `mini_demo` unit tests, Python compilation, Bash syntax, and `git diff --check`.
- [ ] Review the focused diff for secret leakage and unrelated changes.
- [ ] Run three models across all four tasks with `--limit 1`.
- [ ] Verify 12 inference records, Judge finish reasons, scores, and output credential scan.
