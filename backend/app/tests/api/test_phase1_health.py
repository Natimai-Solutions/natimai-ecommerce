from unittest.mock import AsyncMock

import pytest

from app.api.routes.health import healthz_liveness, healthz_ready


class _RedisOk:
    async def __aenter__(self) -> "_RedisOk":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def ping(self) -> bool:
        return True


class _RedisFail:
    async def __aenter__(self) -> "_RedisFail":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
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

    assert response.status == "ready"
    assert response.database is True
    assert response.redis is True


@pytest.mark.anyio
async def test_healthz_ready_returns_degraded_when_dependency_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    session = AsyncMock()
    session.execute = AsyncMock(side_effect=RuntimeError("db down"))

    monkeypatch.setattr("app.api.routes.health.RedisCache", _RedisFail)

    response = await healthz_ready(session=session)

    assert response.status == "degraded"
    assert response.database is False
    assert response.redis is False
