from datetime import datetime
from pathlib import Path

import httpx
import pytest

from backend.app.services.token_usage import (
    MaaSQueryError,
    collect_token_usage,
    fetch_maas_stat,
    split_time_range,
)


ROOT = Path(__file__).resolve().parents[2]


def test_backend_docker_image_installs_httpx_runtime_dependency():
    dockerfile = (ROOT / "deploy_docker/backend/Dockerfile").read_text(encoding="utf-8")

    assert "httpx" in dockerfile


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


@pytest.mark.asyncio
async def test_fetch_maas_stat_sends_names_and_preserves_data():
    observed = {}
    expected = {
        "callCount": 54776,
        "successRate": 85.47,
        "tokenUsage": 10742058,
        "dataTypeList": ["pt", "mc"],
    }

    def handler(request: httpx.Request):
        observed["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"code": 200, "message": "接口访问成功", "data": expected})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await fetch_maas_stat(
            client,
            "http://maas.test/model/stat/query",
            ["name-a", "name-b"],
            datetime(2026, 8, 31, 0),
            datetime(2026, 9, 3, 14),
        )

    assert observed["json"] == {
        "names": ["name-a", "name-b"],
        "startTime": "2026-08-31 00:00:00",
        "endTime": "2026-09-03 14:00:00",
    }
    assert result == expected


@pytest.mark.asyncio
async def test_fetch_maas_stat_rejects_business_error():
    def handler(_: httpx.Request):
        return httpx.Response(200, json={"code": 9999, "message": "查询失败", "data": None})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(MaaSQueryError, match="查询失败"):
            await fetch_maas_stat(
                client,
                "http://maas.test/model/stat/query",
                ["name-a"],
                datetime(2026, 9, 1, 0),
                datetime(2026, 9, 1, 1),
            )


@pytest.mark.asyncio
async def test_collect_uses_independent_full_range_response_as_summary():
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
    assert calls[-1] == (
        ["name-a", "name-b"],
        datetime(2026, 9, 1, 0),
        datetime(2026, 9, 1, 2),
    )


@pytest.mark.asyncio
async def test_collect_keeps_other_rows_when_one_interval_fails():
    async def fake_query(_names, start, _end):
        if start == datetime(2026, 9, 1, 1):
            raise MaaSQueryError("分段超时")
        return {"tokenUsage": start.hour}

    result = await collect_token_usage(
        ["name-a"],
        datetime(2026, 9, 1, 0),
        datetime(2026, 9, 1, 2),
        "hour",
        fake_query,
    )

    assert result["rows"][0]["data"] == {"tokenUsage": 0}
    assert result["rows"][1]["error"] == "分段超时"
    assert result["summary"]["data"] == {"tokenUsage": 0}


def test_token_usage_endpoint_requires_authentication(raw_client):
    response = raw_client.post("/api/v1/token-usage/query", json={
        "names": [{"label": "API A", "value": "name-a"}],
        "startTime": "2026-09-01 00:00:00",
        "endTime": "2026-09-02 00:00:00",
        "granularity": "day",
    })

    assert response.status_code == 401


def test_token_usage_endpoint_passes_values_and_returns_raw_results(client, monkeypatch):
    captured = {}

    async def fake_collect(names, start, end, granularity, query):
        captured.update(names=names, start=start, end=end, granularity=granularity)
        return {
            "rows": [{
                "startTime": "2026-09-01 00:00:00",
                "endTime": "2026-09-02 00:00:00",
                "data": {"tokenUsage": 10, "successRate": 98.2},
            }],
            "summary": {
                "startTime": "2026-09-01 00:00:00",
                "endTime": "2026-09-02 00:00:00",
                "data": {"tokenUsage": 10, "successRate": 98.2},
            },
        }

    monkeypatch.setattr("backend.app.routers.token_usage.collect_token_usage", fake_collect)
    response = client.post("/api/v1/token-usage/query", json={
        "names": [
            {"label": " API A ", "value": " name-a "},
            {"label": "API B", "value": "name-b"},
            {"label": "空值", "value": "   "},
        ],
        "startTime": "2026-09-01 00:00:00",
        "endTime": "2026-09-02 00:00:00",
        "granularity": "day",
    })

    assert response.status_code == 200
    assert captured == {
        "names": ["name-a", "name-b"],
        "start": datetime(2026, 9, 1, 0),
        "end": datetime(2026, 9, 2, 0),
        "granularity": "day",
    }
    body = response.json()
    assert body["names"] == [
        {"label": "API A", "value": "name-a"},
        {"label": "API B", "value": "name-b"},
    ]
    assert body["summary"]["data"] == {"tokenUsage": 10, "successRate": 98.2}


@pytest.mark.parametrize("payload", [
    {
        "names": [{"label": "空值", "value": "  "}],
        "startTime": "2026-09-01 00:00:00",
        "endTime": "2026-09-02 00:00:00",
        "granularity": "day",
    },
    {
        "names": [{"label": "API A", "value": "name-a"}],
        "startTime": "2026-09-02 00:00:00",
        "endTime": "2026-09-01 00:00:00",
        "granularity": "day",
    },
])
def test_token_usage_endpoint_rejects_invalid_query(client, payload):
    response = client.post("/api/v1/token-usage/query", json=payload)

    assert response.status_code == 422
