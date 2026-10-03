from datetime import UTC, datetime

from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

from app.api.deps import SessionDep
from app.core.cache import RedisCache

router = APIRouter(tags=["utils"])


class LivenessResponse(BaseModel):
    """Represents liveness response."""

    status: str
    timestamp: datetime


class ReadinessResponse(BaseModel):
    """Represents readiness response."""

    status: str
    timestamp: datetime
    database: bool
    redis: bool


@router.get("/healthz/liveness", response_model=LivenessResponse)
async def healthz_liveness() -> LivenessResponse:
    """Lightweight liveness probe."""
    return LivenessResponse(status="alive", timestamp=datetime.now(UTC))


@router.get("/healthz/ready", response_model=ReadinessResponse)
async def healthz_ready(session: SessionDep) -> ReadinessResponse | JSONResponse:
    """Readiness probe checking DB and Redis dependencies.

    Returns 200 when both dependencies answer, 503 otherwise — so a load
    balancer or orchestrator probe actually takes the instance out of rotation
    instead of reading a 200 "degraded".
    """
    database_ok = False
    redis_ok = False

    try:
        await session.execute(text("SELECT 1"))
        database_ok = True
    except Exception:  # noqa: BLE001
        database_ok = False

    try:
        async with RedisCache() as cache:
            redis_ok = bool(await cache.ping())
    except Exception:  # noqa: BLE001
        redis_ok = False

    overall_status = "ready" if database_ok and redis_ok else "degraded"

    response = ReadinessResponse(
        status=overall_status,
        timestamp=datetime.now(UTC),
        database=database_ok,
        redis=redis_ok,
    )
    if overall_status != "ready":
        return JSONResponse(status_code=503, content=jsonable_encoder(response))
    return response
