from datetime import datetime, timezone

from fastapi import APIRouter
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
    return LivenessResponse(status="alive", timestamp=datetime.now(timezone.utc))


@router.get("/healthz/ready", response_model=ReadinessResponse)
async def healthz_ready(session: SessionDep) -> ReadinessResponse:
    """Readiness probe checking DB and Redis dependencies."""
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

    return ReadinessResponse(
        status=overall_status,
        timestamp=datetime.now(timezone.utc),
        database=database_ok,
        redis=redis_ok,
    )
