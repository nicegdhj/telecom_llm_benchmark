# MaaS Token Usage Query Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an authenticated Score Platform page that queries MaaS token statistics by editable Name identifiers, displays hourly or daily interval responses, and shows the MaaS full-range response as the summary without recalculation.

**Architecture:** The React page sends one request to a FastAPI proxy. The backend validates the query, splits the requested range, calls the private MaaS endpoint with at most four concurrent requests, performs one additional full-range request for the summary, and returns raw MaaS metric objects plus per-request errors.

**Tech Stack:** React 19, React Router, TanStack Query, Tailwind CSS, FastAPI, Pydantic v2, HTTPX, pytest.

---

## File map

- Create `backend/app/services/token_usage.py`: time segmentation, MaaS HTTP call, bounded query orchestration.
- Create `backend/app/routers/token_usage.py`: authenticated Score API endpoint.
- Create `backend/tests/test_token_usage.py`: service and endpoint behavior tests.
- Modify `backend/app/config.py`: configurable private MaaS statistics URL and timeout.
- Modify `backend/app/schemas.py`: request and response models.
- Modify `backend/app/main.py`: register the router.
- Modify `backend/pyproject.toml`: make HTTPX a runtime dependency.
- Modify `deploy_docker/backend/Dockerfile`: install HTTPX in the production backend image, whose dependency list is explicit.
- Create `frontend/src/features/tokenUsage/tokenUsageConfig.js`: default K-V Names and metric column metadata.
- Create `frontend/src/features/tokenUsage/tokenUsageConfig.test.mjs`: dependency-free Node tests for defaults and columns.
- Create `frontend/src/features/tokenUsage/TokenUsagePage.jsx`: query form and horizontally scrollable result table.
- Modify `frontend/src/lib/api.js`: token usage query client.
- Modify `frontend/src/App.jsx`: page route.
- Modify `frontend/src/components/layout/Sidebar.jsx`: left navigation entry.
- Modify `deploy_docker/docker-compose.yml`: pass the configurable MaaS endpoint into the backend container.

### Task 1: Backend time segmentation and MaaS query service

**Files:**
- Create: `backend/tests/test_token_usage.py`
- Create: `backend/app/services/token_usage.py`
- Modify: `backend/pyproject.toml`
- Modify: `deploy_docker/backend/Dockerfile`

- [ ] **Step 1: Write failing segmentation tests**

Add tests that call `split_time_range()` with Beijing-local naive datetimes and assert exact interval boundaries:

```python
def test_split_day_keeps_partial_first_and_last_intervals():
    start = datetime(2026, 8, 31, 10)
    end = datetime(2026, 9, 2, 14)
    assert split_time_range(start, end, "day") == [
        (datetime(2026, 8, 31, 10), datetime(2026, 9, 1, 0)),
        (datetime(2026, 9, 1, 0), datetime(2026, 9, 2, 0)),
        (datetime(2026, 9, 2, 0), datetime(2026, 9, 2, 14)),
    ]


def test_split_hour_uses_one_hour_intervals():
    start = datetime(2026, 9, 1, 10)
    end = datetime(2026, 9, 1, 13)
    assert split_time_range(start, end, "hour") == [
        (datetime(2026, 9, 1, 10), datetime(2026, 9, 1, 11)),
        (datetime(2026, 9, 1, 11), datetime(2026, 9, 1, 12)),
        (datetime(2026, 9, 1, 12), datetime(2026, 9, 1, 13)),
    ]
```

- [ ] **Step 2: Run tests and verify RED**

Run:

```bash
pytest -q backend/tests/test_token_usage.py
```

Expected: collection fails because `backend.app.services.token_usage` does not exist.

- [ ] **Step 3: Implement the smallest correct splitter**

Implement `split_time_range(start, end, granularity)` using `timedelta(hours=1)` for hourly queries and the next local midnight for daily queries. Raise `ValueError` when `end <= start` or granularity is unsupported.

```python
def split_time_range(start: datetime, end: datetime, granularity: str):
    if end <= start:
        raise ValueError("endTime 必须晚于 startTime")
    if granularity not in {"hour", "day"}:
        raise ValueError("不支持的统计维度")

    result = []
    cursor = start
    while cursor < end:
        if granularity == "hour":
            boundary = cursor + timedelta(hours=1)
        else:
            boundary = datetime.combine(cursor.date() + timedelta(days=1), time.min)
        next_cursor = min(boundary, end)
        result.append((cursor, next_cursor))
        cursor = next_cursor
    return result
```

- [ ] **Step 4: Add failing MaaS pass-through tests**

Use `httpx.MockTransport` to verify that both Name values and formatted time strings are sent, and that the returned `data` mapping is preserved exactly. Add an orchestration test with an injected async query function to verify that interval results and the independent full-range response are not combined or averaged.

```python
async def test_collect_uses_full_range_response_as_summary():
    calls = []

    async def fake_query(names, start, end):
        calls.append((names, start, end))
        return {"tokenUsage": len(calls) * 100, "successRate": 80 + len(calls)}

    result = await collect_token_usage(
        ["name-a", "name-b"],
        datetime(2026, 9, 1, 0),
        datetime(2026, 9, 1, 2),
        "hour",
        fake_query,
    )
    assert [row["data"]["tokenUsage"] for row in result["rows"]] == [100, 200]
    assert result["summary"]["data"] == {"tokenUsage": 300, "successRate": 83}
    assert calls[-1][1:] == (datetime(2026, 9, 1, 0), datetime(2026, 9, 1, 2))
```

- [ ] **Step 5: Implement HTTP querying and bounded orchestration**

Implement:

- `format_maas_time(value)` returning `%Y-%m-%d %H:%M:%S`.
- `fetch_maas_stat(client, url, names, start, end)` posting only `names`, `startTime`, and `endTime`; validate HTTP success, JSON object shape, and business `code == 200`; return `payload["data"]` unchanged.
- `collect_token_usage(...)` running interval calls with `asyncio.Semaphore(4)`, preserving chronological row order, capturing each failure into that row, and making one independent full-range call for `summary`.

Every row must have `startTime`, `endTime`, and exactly one of `data` or `error`. `summary` follows the same shape.

- [ ] **Step 6: Run backend service tests and verify GREEN**

Run:

```bash
pytest -q backend/tests/test_token_usage.py
```

Expected: all service tests pass.

- [ ] **Step 7: Verify the production image includes HTTPX**

Add a test that reads `deploy_docker/backend/Dockerfile` and requires `httpx` in its explicit `pip install` dependency list. Run the test once before editing the Dockerfile to verify it fails, then append `httpx` to that list and verify it passes.

- [ ] **Step 8: Commit service behavior**

```bash
git add backend/app/services/token_usage.py backend/tests/test_token_usage.py backend/pyproject.toml deploy_docker/backend/Dockerfile
git commit -m "feat: add MaaS token usage query service"
```

### Task 2: Authenticated Score API endpoint

**Files:**
- Modify: `backend/tests/test_token_usage.py`
- Modify: `backend/app/config.py`
- Modify: `backend/app/schemas.py`
- Create: `backend/app/routers/token_usage.py`
- Modify: `backend/app/main.py`

- [ ] **Step 1: Write failing API tests**

Add endpoint tests for authentication, input validation, K-V normalization, and response pass-through. Patch the router's orchestration function so tests do not use the network.

```python
def test_token_usage_endpoint_passes_values_and_returns_raw_results(client, monkeypatch):
    captured = {}

    async def fake_collect(names, start, end, granularity, query):
        captured.update(names=names, start=start, end=end, granularity=granularity)
        return {
            "rows": [{
                "startTime": "2026-09-01 00:00:00",
                "endTime": "2026-09-02 00:00:00",
                "data": {"tokenUsage": 10},
            }],
            "summary": {
                "startTime": "2026-09-01 00:00:00",
                "endTime": "2026-09-02 00:00:00",
                "data": {"tokenUsage": 10},
            },
        }

    monkeypatch.setattr("backend.app.routers.token_usage.collect_token_usage", fake_collect)
    response = client.post("/api/v1/token-usage/query", json={
        "names": [
            {"label": "API A", "value": "name-a"},
            {"label": "API B", "value": "name-b"},
        ],
        "startTime": "2026-09-01 00:00:00",
        "endTime": "2026-09-02 00:00:00",
        "granularity": "day",
    })
    assert response.status_code == 200
    assert captured["names"] == ["name-a", "name-b"]
    assert response.json()["summary"]["data"]["tokenUsage"] == 10
```

Also assert `422` for no non-empty Name values and for `endTime <= startTime`, plus `401` from an unauthenticated request.

- [ ] **Step 2: Run endpoint tests and verify RED**

Run:

```bash
pytest -q backend/tests/test_token_usage.py
```

Expected: endpoint tests fail with route-not-found or import errors.

- [ ] **Step 3: Add schemas, configuration, and router**

Add Pydantic models with aliases matching the frontend payload:

```python
class TokenUsageName(BaseModel):
    label: str = ""
    value: str


class TokenUsageQueryIn(BaseModel):
    names: list[TokenUsageName] = Field(..., min_length=1)
    start_time: datetime = Field(alias="startTime")
    end_time: datetime = Field(alias="endTime")
    granularity: Literal["hour", "day"] = "day"
```

Add these settings:

```python
maas_stat_url: str = "http://188.108.11.94:31567/model/stat/query"
maas_stat_timeout_sec: float = 120.0
```

The router must:

- Require `viewer`, `operator`, or `admin`.
- Trim labels and values and reject an empty effective Name list.
- Reject `endTime <= startTime`.
- Reject timezone-aware values, more than 20 Names, Name values longer than 200 characters, and queries that produce more than 744 intervals.
- Create one `httpx.AsyncClient` with the configured timeout.
- Pass a closure using `fetch_maas_stat()` into `collect_token_usage()`.
- Return the normalized K-V list alongside `rows` and `summary`.

Register the router in `backend/app/main.py`.

- [ ] **Step 4: Run endpoint tests and verify GREEN**

Run:

```bash
pytest -q backend/tests/test_token_usage.py
```

Expected: all token usage tests pass.

- [ ] **Step 5: Run the existing backend suite**

Run:

```bash
pytest -q backend/tests
```

Expected: all backend tests pass with no new failures.

- [ ] **Step 6: Commit the endpoint**

```bash
git add backend/app/config.py backend/app/schemas.py backend/app/routers/token_usage.py backend/app/main.py backend/tests/test_token_usage.py
git commit -m "feat: expose token usage query API"
```

### Task 3: Token usage page, navigation, and deployment configuration

**Files:**
- Create: `frontend/src/features/tokenUsage/tokenUsageConfig.test.mjs`
- Create: `frontend/src/features/tokenUsage/tokenUsageConfig.js`
- Create: `frontend/src/features/tokenUsage/TokenUsagePage.jsx`
- Modify: `frontend/src/lib/api.js`
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/components/layout/Sidebar.jsx`
- Modify: `deploy_docker/docker-compose.yml`

- [ ] **Step 1: Write a failing dependency-free frontend configuration test**

Create a Node test that imports the not-yet-created configuration module and verifies the two default Name values and all MaaS data keys required by the design:

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import { DEFAULT_NAMES, METRIC_COLUMNS } from './tokenUsageConfig.js';

test('provides the two editable default MaaS names', () => {
  assert.deepEqual(DEFAULT_NAMES.map((item) => item.value), [
    'd29a854f-5b1f-4da9-9a1e-caecacfd1156',
    '76816616-c232-404c-bbb8-c950549231ee',
  ]);
});

test('lists every metric returned by the MaaS statistics API', () => {
  assert.deepEqual(METRIC_COLUMNS.map((item) => item.key), [
    'keyNum', 'serviceNum', 'apiNum', 'callCount', 'exceptionCount',
    'successRate', 'tokenUsage', 'avgTokenUsage', 'avgRequestTokenUsage',
    'avgDelay', 'avgTimeToFirstToken', 'avgTokenSpeed', 'avgTokenThroughput',
    'httpClientErrorAlerts', 'httpServerErrorAlerts', 'avgEndToEndTps',
    'avgModelOutputTokenTps', 'timeToPerToken', 'dataTypeList',
  ]);
});
```

- [ ] **Step 2: Run the frontend test and verify RED**

Run:

```bash
node --test frontend/src/features/tokenUsage/tokenUsageConfig.test.mjs
```

Expected: module-not-found failure for `tokenUsageConfig.js`.

- [ ] **Step 3: Add defaults and display metadata**

Create `tokenUsageConfig.js` containing:

- Two default K-V rows with labels `接口 1` and `接口 2`.
- The 19 metric definitions in API order.
- Chinese column labels.
- A formatter type for plain numbers, percentage, milliseconds, and string lists.

Run the Node test again and expect both tests to pass.

- [ ] **Step 4: Add the API client and page**

Add this client method to `frontend/src/lib/api.js`:

```javascript
tokenUsage: {
  query: (data) => request('/token-usage/query', {
    method: 'POST',
    body: JSON.stringify(data),
  }),
},
```

Implement `TokenUsagePage.jsx` with:

- A compact white query card consistent with the existing Score platform.
- Two `datetime-local` fields using `step="3600"` and values normalized to whole hours.
- A day/hour segmented control, defaulting to day.
- Editable K-V Name rows with add and delete controls.
- Client-side validation matching the backend rules.
- `useMutation` calling `api.tokenUsage.query()`.
- A result context strip showing submitted K-V Names.
- A horizontally scrollable table whose sticky first column is the interval.
- One body row per backend `rows` item and one visually distinct final `summary` row.
- Exact MaaS values with display-only `%` and `ms` suffixes.
- Per-row error text without inventing metric values.
- Loading, empty, and query-level error states.
- Clear the previous successful result immediately before a valid new query so a failed request cannot leave stale data visible.

- [ ] **Step 5: Register route and navigation**

Import `TokenUsagePage` in `frontend/src/App.jsx` and add:

```jsx
{ path: 'token-usage', element: <TokenUsagePage /> },
```

Add a Sidebar item using an existing Lucide token/usage-appropriate icon:

```javascript
{ to: '/token-usage', icon: Gauge, label: 'Token用量查询' }
```

- [ ] **Step 6: Pass the private URL into the backend container**

Add this single environment entry under `score-backend` without changing adjacent deployment settings:

```yaml
- EVAL_BACKEND_MAAS_STAT_URL=${EVAL_BACKEND_MAAS_STAT_URL:-http://188.108.11.94:31567/model/stat/query}
```

- [ ] **Step 7: Verify frontend and integrated backend behavior**

Run:

```bash
node --test frontend/src/features/tokenUsage/tokenUsageConfig.test.mjs
npm --prefix frontend run lint
npm --prefix frontend run build
pytest -q backend/tests/test_token_usage.py
```

Expected: all commands pass; Vite emits a production build with the new route.

- [ ] **Step 8: Commit the page and deployment setting**

```bash
git add frontend/src/features/tokenUsage frontend/src/lib/api.js frontend/src/App.jsx frontend/src/components/layout/Sidebar.jsx deploy_docker/docker-compose.yml
git commit -m "feat: add Token usage query page"
```

### Task 4: Final regression and implementation review

**Files:**
- Verify only; no planned source changes.

- [ ] **Step 1: Run focused and full checks**

```bash
pytest -q backend/tests/test_token_usage.py
pytest -q backend/tests
node --test frontend/src/features/tokenUsage/tokenUsageConfig.test.mjs
npm --prefix frontend run lint
npm --prefix frontend run build
git diff --check HEAD~3..HEAD
```

Expected: all tests and builds pass, and no whitespace errors are reported.

- [ ] **Step 2: Review scope and data semantics**

Confirm from the final diff that:

- Only the files listed in this plan changed.
- The backend always sends the current non-empty Name values to every MaaS request.
- Daily intervals split at midnight and never extend beyond the selected time range.
- The summary comes from an independent full-range MaaS response.
- No metric is added, averaged, inferred, or recalculated by Score.
- Existing unrelated working-tree modifications were not staged or changed.

- [ ] **Step 3: Hand off private-network verification command**

Provide the user with the page URL and the environment variable required if the private endpoint differs from the default. State that actual MaaS connectivity can only be confirmed after deployment inside the private network.
