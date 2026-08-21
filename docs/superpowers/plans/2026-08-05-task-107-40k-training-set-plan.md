# Task 107 40K Training Set Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generate a deterministic, balanced 40,000-row Task 107 SFT dataset with zero exact test leakage and explicit coverage of the model's current false-negative attack types.

**Architecture:** Refactor the existing single-use builder into testable pure selection helpers plus a thin file-writing `main`. Preserve valid existing rows first, classify Yes candidates with mutually exclusive audit categories, include every available targeted candidate, and fill the remainder deterministically. Produce a JSON audit report and independently verify the generated JSONL against both test workbooks.

**Tech Stack:** Python 3.10+, pandas/openpyxl for workbook input, pytest, JSONL, LLaMA-Factory ShareGPT format.

## Global Constraints

- Final dataset contains exactly 40,000 unique Payloads: 20,000 Yes and 20,000 No.
- Exact normalized Payload overlap with the full test workbook and label-review workbook is zero.
- Existing valid 8,000 training rows are preserved.
- Same-type coverage uses only different real source rows; no generated or modified test Payloads.
- Seed remains `107`; system prompt and ShareGPT message schema remain unchanged.
- Do not touch unrelated dirty-worktree files and do not create a git commit unless the user requests one.

---

### Task 1: Test the classification and balanced selection contract

**Files:**
- Create: `tests/test_build_task_107_lora_train.py`
- Modify: `scripts/build_task_107_lora_train.py`

**Interfaces:**
- Consumes: normalized candidate dictionaries containing `payload_norm`, `gold`, and `other_wrong`.
- Produces: `classify_yes_case(payload: str) -> str` and `select_training_rows(candidates, existing_rows, forbidden_payloads, target_per_label, seed) -> tuple[list[dict], dict]`.

- [ ] **Step 1: Write failing category tests**

```python
@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ("POST /login HTTP/1.1\n\nusername=root&password=123456", "login_plaintext"),
        ("GET / HTTP/1.1\nUser-Agent: zgrab/0.x", "scanner_user_agent"),
        ("CONNECT 1.2.3.4:443 HTTP/1.1", "connect_tunnel"),
        ("GET /druid/index.html HTTP/1.1", "admin_api_probe"),
        ("GET /probe.jsp HTTP/1.1", "dynamic_script_path"),
        ("GET /?id=1 UNION SELECT password FROM users HTTP/1.1", "strong_attack_rule"),
        ("GET /assets/main.css HTTP/1.1", "other_yes"),
    ],
)
def test_classify_yes_case_uses_mutually_exclusive_priority(payload, expected):
    assert classify_yes_case(payload) == expected
```

- [ ] **Step 2: Run the category test and verify it fails because the interface is absent**

Run: `env PYTHONPATH=. pytest -q tests/test_build_task_107_lora_train.py -k classify`

Expected: collection failure for missing `classify_yes_case`.

- [ ] **Step 3: Write failing selection tests**

Create small in-memory candidates that prove the selector preserves valid existing rows, excludes forbidden Payloads, includes every targeted Yes category, fills both labels to the requested count, and is deterministic for the same seed.

- [ ] **Step 4: Run selection tests and verify failure because selection behavior is absent**

Run: `env PYTHONPATH=. pytest -q tests/test_build_task_107_lora_train.py -k select`

Expected: failure for missing `select_training_rows` or incorrect selection behavior.

- [ ] **Step 5: Implement the smallest pure helpers that satisfy the tests**

Add compiled category patterns, reuse `match_rules` for strong signatures, remove forbidden/duplicate rows before selection, preserve valid existing rows, select all targeted Yes rows in priority order, and fill remaining slots using hard cases then seeded random candidates.

- [ ] **Step 6: Run the focused tests**

Run: `env PYTHONPATH=. pytest -q tests/test_build_task_107_lora_train.py`

Expected: all tests pass.

### Task 2: Integrate workbook loading, report generation, and 40K configuration

**Files:**
- Modify: `scripts/build_task_107_lora_train.py`
- Modify: `mydata/task_107/lora/qwen3_6_27b_lora_sft.yaml`
- Test: `tests/test_build_task_107_lora_train.py`

**Interfaces:**
- Consumes: source workbook, full test workbook, label-review workbook, and existing JSONL.
- Produces: 40K JSONL plus `build_report.json`, unchanged dataset registration, and `max_samples: 40000`.

- [ ] **Step 1: Write a failing report test**

Assert that the report contains total/label/unique counts, preserved and added counts, both exact-overlap counters, final and added category coverage, hard-case counts, and error-family overlap.

- [ ] **Step 2: Run the report test and verify expected missing-field failure**

Run: `env PYTHONPATH=. pytest -q tests/test_build_task_107_lora_train.py -k report`

- [ ] **Step 3: Implement workbook/review/existing-data loading and report fields**

Keep `main()` as orchestration only. Set `TARGET_PER_LABEL = 20000`, include review Payloads in the forbidden set, retain the existing system prompt, and write files atomically through temporary files followed by replacement.

- [ ] **Step 4: Update the LLaMA-Factory cap**

Change only `max_samples: 8000` to `max_samples: 40000` in `qwen3_6_27b_lora_sft.yaml`.

- [ ] **Step 5: Run all builder tests**

Run: `env PYTHONPATH=. pytest -q tests/test_build_task_107_lora_train.py`

Expected: all tests pass.

### Task 3: Build and independently audit the final artifacts

**Files:**
- Regenerate: `mydata/task_107/train/task_107_lora_train.jsonl`
- Regenerate: `mydata/task_107/train/build_report.json`
- Regenerate: `mydata/task_107/train/dataset_info.json`
- Regenerate: `mydata/task_107/train/system_prompt.txt`

**Interfaces:**
- Consumes: the completed builder and immutable source/test workbooks.
- Produces: deployable Task 107 training artifacts and fresh verification evidence.

- [ ] **Step 1: Run the builder**

Run: `env PYTHONPATH=. python scripts/build_task_107_lora_train.py`

Expected: report shows 40,000 rows, 20,000 per label, and both overlap counters equal zero.

- [ ] **Step 2: Independently parse and audit every JSONL row**

Run a separate read-only audit that verifies valid JSON, exact ShareGPT role order, one system prompt variant, 40,000 unique Payloads, 20,000 labels each, and zero normalized overlap with both test sources.

- [ ] **Step 3: Verify preservation and coverage**

Compare the pre-build 8,000 Payload hashes captured by the builder report against the final set, assert all valid rows remain, assert all available targeted Yes candidate hashes are selected, and reconcile category totals with the report.

- [ ] **Step 4: Verify deterministic output**

Hash the generated JSONL and report, rerun the builder, and assert both hashes remain unchanged.

- [ ] **Step 5: Run focused regression tests and diff checks**

Run: `env PYTHONPATH=. pytest -q tests/test_build_task_107_lora_train.py tests/test_review_task_107_labels.py`

Run: `git diff --check`

Expected: tests pass and diff check exits zero.
