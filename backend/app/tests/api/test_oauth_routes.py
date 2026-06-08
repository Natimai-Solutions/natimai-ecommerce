"""Contract tests for social OAuth endpoints (/auth/{provider}/...).

The security-critical guarantee under test: an inactive user must never obtain
JWT tokens through social login — parity with classic password authentication.
"""

import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

import app.api.routes.oauth as oauth_module
from app.api.deps import get_redis_cache
from app.core.db import get_db
from app.main import app


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace(rollback=AsyncMock(), commit=AsyncMock())


@pytest.fixture
def fake_redis() -> SimpleNamespace:
    # getdel returns the provider name (bytes) to satisfy state verification.
    return SimpleNamespace(
        setex=AsyncMock(),
        getdel=AsyncMock(return_value=b"google"),
    )


@pytest.fixture(autouse=True)
def override_dependencies(
    db_session: SimpleNamespace,
    fake_redis: SimpleNamespace,
) -> Generator[None, None, None]:
    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    async def _override_get_redis() -> AsyncGenerator[SimpleNamespace, None]:
        yield fake_redis

    app.dependency_overrides[get_db] = _override_get_db
    app.dependency_overrides[get_redis_cache] = _override_get_redis
    yield
    app.dependency_overrides.clear()


def test_login_unsupported_provider_returns_400(client: TestClient) -> None:
    response = client.get("/api/v1/auth/facebook/login", follow_redirects=False)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "oauth.provider.unsupported"


def test_callback_invalid_state_redirects_with_error(
    client: TestClient,
    fake_redis: SimpleNamespace,
) -> None:
    fake_redis.getdel = AsyncMock(return_value=None)  # state expired / unknown

    response = client.get(
        "/api/v1/auth/google/callback?code=abc&state=xyz",
        follow_redirects=False,
    )

    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["oauth_error"] == ["invalid_state"]


def test_callback_inactive_user_is_blocked_and_issues_no_token(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inactive_user = SimpleNamespace(id=uuid.uuid4(), is_active=False)

    monkeypatch.setattr(
        oauth_module, "_exchange_code", AsyncMock(return_value={"access_token": "tok"})
    )
    monkeypatch.setattr(
        oauth_module, "_fetch_user_info", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        oauth_module,
        "_extract_user_info",
        lambda _provider, _info: ("uid-123", "blocked@example.com", "Blocked User"),
    )
    monkeypatch.setattr(
        oauth_module, "_find_or_create_user", AsyncMock(return_value=inactive_user)
    )
    create_token_spy = AsyncMock()
    monkeypatch.setattr(
        oauth_module.crud_user_refresh_token, "create_for_user", create_token_spy
    )

    response = client.get(
        "/api/v1/auth/google/callback?code=abc&state=valid",
        follow_redirects=False,
    )

    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["oauth_error"] == ["user_inactive"]
    # No JWT must ever be minted for an inactive account.
    create_token_spy.assert_not_awaited()


def test_callback_active_user_redirects_with_tokens(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_user = SimpleNamespace(id=uuid.uuid4(), is_active=True)

    monkeypatch.setattr(
        oauth_module, "_exchange_code", AsyncMock(return_value={"access_token": "tok"})
    )
    monkeypatch.setattr(
        oauth_module, "_fetch_user_info", AsyncMock(return_value={})
    )
    monkeypatch.setattr(
        oauth_module,
        "_extract_user_info",
        lambda _provider, _info: ("uid-999", "ok@example.com", "Active User"),
    )
    monkeypatch.setattr(
        oauth_module, "_find_or_create_user", AsyncMock(return_value=active_user)
    )
    monkeypatch.setattr(
        oauth_module.crud_user_refresh_token, "create_for_user", AsyncMock()
    )

    response = client.get(
        "/api/v1/auth/google/callback?code=abc&state=valid",
        follow_redirects=False,
    )

    assert response.status_code == 302
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert "access_token" in query
    assert "refresh_token" in query
    assert "oauth_error" not in query
