import httpx
from fastapi import APIRouter, Depends, HTTPException

from backend.app.config import get_settings
from backend.app.deps import require_role
from backend.app.models import User
from backend.app.schemas import TokenUsageQueryIn
from backend.app.services.token_usage import collect_token_usage, fetch_maas_stat


router = APIRouter(prefix="/api/v1/token-usage", tags=["token-usage"])


@router.post("/query")
async def query_token_usage(
    payload: TokenUsageQueryIn,
    _: User = Depends(require_role("viewer", "operator", "admin")),
):
    names = [
        {"label": item.label.strip(), "value": item.value.strip()}
        for item in payload.names
        if item.value.strip()
    ]
    if not names:
        raise HTTPException(status_code=422, detail="至少填写一个 Name 值")

    settings = get_settings()
    async with httpx.AsyncClient(timeout=settings.maas_stat_timeout_sec) as client:
        async def query(names_values, start, end):
            return await fetch_maas_stat(
                client,
                settings.maas_stat_url,
                names_values,
                start,
                end,
            )

        try:
            result = await collect_token_usage(
                [item["value"] for item in names],
                payload.start_time,
                payload.end_time,
                payload.granularity,
                query,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {"names": names, **result}
