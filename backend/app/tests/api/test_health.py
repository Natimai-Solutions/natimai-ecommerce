import json
from types import TracebackType
from unittest.mock import AsyncMock

import pytest
from fastapi.responses import JSONResponse

from app.api.routes.health import ReadinessResponse, healthz_liveness, healthz_ready


class _RedisOk:
    async def __aenter__(self) -> "_RedisOk":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    async def ping(self) -> bool:
        return True


class _RedisFail:
    async def __aenter__(self) -> "_RedisFail":
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> bool:
        return False

    async def ping(self) -> bool:
        return False


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_healthz_liveness_returns_alive() -> None:
    response = await healthz_liveness()
    assert response.status == "alive"


@pytest.mark.anyio
async def test_healthz_ready_returns_ready_when_dependencies_are_up(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.execute = AsyncMock(return_value=1)

    monkeypatch.setattr("app.api.routes.health.RedisCache", _RedisOk)

    response = await healthz_ready(session=session)

    assert isinstance(response, ReadinessResponse)
    assert response.status == "ready"
    assert response.database is True
    assert response.redis is True


@pytest.mark.anyio
async def test_healthz_ready_returns_503_when_dependency_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A degraded readiness must be a 503 so LB/orchestrator probes see it."""
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db down"))

    monkeypatch.setattr("app.api.routes.health.RedisCache", _RedisFail)

    response = await healthz_ready(session=session)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503
    payload = json.loads(bytes(response.body).decode("utf-8"))
    assert payload["status"] == "degraded"
    assert payload["database"] is False
    assert payload["redis"] is False
