"""Tests for login hardening: per-IP throttle, lockout mapping, client IP.

The rate limiter itself is exercised against the real Redis of the dev stack
(unique keys per run); the HTTP contracts are tested with the limiter mocked.
"""

import datetime
import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

import app.api.routes.login as login_routes
from app.core.config import settings
from app.core.db import get_db
from app.core.rate_limit import get_client_ip, hit_rate_limit
from app.features.user.crud.user import AccountLockedError, crud_user
from app.main import app


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


# --------------------------------------------------------------------------
# get_client_ip — proxy awareness
# --------------------------------------------------------------------------


def _request(headers: dict[str, str], host: str = "10.0.0.1") -> SimpleNamespace:
    return SimpleNamespace(headers=headers, client=SimpleNamespace(host=host))


def test_client_ip_uses_socket_peer_by_default() -> None:
    request = _request({"X-Forwarded-For": "1.2.3.4"})
    # Header NOT trusted unless explicitly configured (spoofable).
    assert get_client_ip(request) == "10.0.0.1"  # type: ignore[arg-type]


def test_client_ip_reads_configured_proxy_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CLIENT_IP_HEADER", "CF-Connecting-IP")
    request = _request({"CF-Connecting-IP": "203.0.113.7"})
    assert get_client_ip(request) == "203.0.113.7"  # type: ignore[arg-type]


def test_client_ip_takes_last_entry_of_forwarded_chain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The LAST XFF entry is the one appended by our own proxy; earlier
    entries are client-supplied and forgeable (throttle bypass otherwise)."""
    monkeypatch.setattr(settings, "CLIENT_IP_HEADER", "X-Forwarded-For")
    request = _request({"X-Forwarded-For": "spoofed.invalid, 172.16.0.1, 203.0.113.7"})
    assert get_client_ip(request) == "203.0.113.7"  # type: ignore[arg-type]


def test_client_ip_falls_back_when_header_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "CLIENT_IP_HEADER", "CF-Connecting-IP")
    request = _request({})
    assert get_client_ip(request) == "10.0.0.1"  # type: ignore[arg-type]


# --------------------------------------------------------------------------
# hit_rate_limit — real Redis (dev stack), unique key per run
# --------------------------------------------------------------------------


@pytest.mark.anyio
async def test_hit_rate_limit_counts_within_window() -> None:
    key = f"test:{uuid.uuid4().hex}"
    assert await hit_rate_limit(key, limit=2, window_seconds=60) is False
    assert await hit_rate_limit(key, limit=2, window_seconds=60) is False
    assert await hit_rate_limit(key, limit=2, window_seconds=60) is True


# --------------------------------------------------------------------------
# HTTP contracts on POST /login/access-token
# --------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def override_db() -> Generator[None, None, None]:
    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_login_returns_429_when_rate_limited(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(login_routes, "hit_rate_limit", AsyncMock(return_value=True))

    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "a@b.c", "password": "x"},
    )

    assert response.status_code == 429
    assert response.json()["error"]["code"] == "login.rate_limited"


def test_login_returns_429_when_account_locked(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(login_routes, "hit_rate_limit", AsyncMock(return_value=False))
    locked_until = datetime.datetime(2026, 1, 1, 12, 0, 0)
    monkeypatch.setattr(
        crud_user,
        "authenticate",
        AsyncMock(side_effect=AccountLockedError(locked_until)),
    )

    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "a@b.c", "password": "x"},
    )

    assert response.status_code == 429
    payload = response.json()["error"]
    assert payload["code"] == "login.account.locked"
    assert payload["details"]["locked_until"] == locked_until.isoformat()
