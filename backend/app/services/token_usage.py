import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, time, timedelta
from typing import Any

import httpx


MaaSQuery = Callable[[list[str], datetime, datetime], Awaitable[dict[str, Any]]]


class MaaSQueryError(RuntimeError):
    pass


def format_maas_time(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S")


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


async def fetch_maas_stat(
    client: httpx.AsyncClient,
    url: str,
    names: list[str],
    start: datetime,
    end: datetime,
) -> dict[str, Any]:
    try:
        response = await client.post(
            url,
            json={
                "names": names,
                "startTime": format_maas_time(start),
                "endTime": format_maas_time(end),
            },
        )
        response.raise_for_status()
    except httpx.HTTPError as exc:
        raise MaaSQueryError(f"MaaS 请求失败：{exc}") from exc

    try:
        payload = response.json()
    except ValueError as exc:
        raise MaaSQueryError("MaaS 返回了非 JSON 响应") from exc

    if not isinstance(payload, dict):
        raise MaaSQueryError("MaaS 返回格式错误")
    if payload.get("code") != 200:
        raise MaaSQueryError(str(payload.get("message") or "MaaS 查询失败"))
    if not isinstance(payload.get("data"), dict):
        raise MaaSQueryError("MaaS 返回缺少 data")
    return payload["data"]


async def collect_token_usage(
    names: list[str],
    start: datetime,
    end: datetime,
    granularity: str,
    query: MaaSQuery,
) -> dict[str, Any]:
    intervals = split_time_range(start, end, granularity)
    semaphore = asyncio.Semaphore(4)

    async def run_interval(interval_start: datetime, interval_end: datetime):
        row = {
            "startTime": format_maas_time(interval_start),
            "endTime": format_maas_time(interval_end),
        }
        try:
            async with semaphore:
                row["data"] = await query(names, interval_start, interval_end)
        except Exception as exc:
            row["error"] = str(exc)
        return row

    rows = await asyncio.gather(*(run_interval(a, b) for a, b in intervals))
    summary = {
        "startTime": format_maas_time(start),
        "endTime": format_maas_time(end),
    }
    try:
        summary["data"] = await query(names, start, end)
    except Exception as exc:
        summary["error"] = str(exc)

    return {"rows": rows, "summary": summary}
