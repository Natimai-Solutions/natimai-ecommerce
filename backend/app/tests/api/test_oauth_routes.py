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
from app.core.config import settings
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
    inactive_user = SimpleNamespace(
        id=uuid.uuid4(), is_active=False, is_superuser=False
    )

    monkeypatch.setattr(
        oauth_module, "_exchange_code", AsyncMock(return_value={"access_token": "tok"})
    )
    monkeypatch.setattr(oauth_module, "_fetch_user_info", AsyncMock(return_value={}))
    monkeypatch.setattr(
        oauth_module,
        "_extract_user_info",
        lambda _provider, _info, _claims: oauth_module.OAuthIdentity(
            "uid-123", "blocked@example.com", "Blocked User", email_verified=True
        ),
    )
    monkeypatch.setattr(
        oauth_module, "_find_or_create_user", AsyncMock(return_value=inactive_user)
    )
    create_token_spy = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.oauth.crud_user_refresh_token.create_for_user",
        create_token_spy,
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


def test_callback_active_user_sets_refresh_cookie(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    active_user = SimpleNamespace(id=uuid.uuid4(), is_active=True, is_superuser=False)

    monkeypatch.setattr(
        oauth_module, "_exchange_code", AsyncMock(return_value={"access_token": "tok"})
    )
    monkeypatch.setattr(oauth_module, "_fetch_user_info", AsyncMock(return_value={}))
    monkeypatch.setattr(
        oauth_module,
        "_extract_user_info",
        lambda _provider, _info, _claims: oauth_module.OAuthIdentity(
            "uid-999", "ok@example.com", "Active User", email_verified=True
        ),
    )
    monkeypatch.setattr(
        oauth_module, "_find_or_create_user", AsyncMock(return_value=active_user)
    )
    monkeypatch.setattr(
        "app.api.routes.oauth.crud_user_refresh_token.create_for_user", AsyncMock()
    )

    response = client.get(
        "/api/v1/auth/google/callback?code=abc&state=valid",
        follow_redirects=False,
    )

    assert response.status_code == 302
    # No token must travel in the URL anymore — only the HttpOnly refresh cookie.
    query = parse_qs(urlparse(response.headers["location"]).query)
    assert "access_token" not in query
    assert "refresh_token" not in query
    assert "oauth_error" not in query
    assert response.cookies.get(settings.REFRESH_COOKIE_NAME)


def _stub_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        oauth_module, "_exchange_code", AsyncMock(return_value={"access_token": "tok"})
    )
    monkeypatch.setattr(oauth_module, "_fetch_user_info", AsyncMock(return_value={}))
    monkeypatch.setattr(
        oauth_module,
        "_extract_user_info",
        lambda _provider, _info, _claims: oauth_module.OAuthIdentity(
            "uid-1", "victim@example.com", "Victim", email_verified=False
        ),
    )


def test_callback_refused_identity_redirects_with_its_reason(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session: SimpleNamespace,
) -> None:
    _stub_provider(monkeypatch)
    monkeypatch.setattr(
        oauth_module,
        "_find_or_create_user",
        AsyncMock(
            side_effect=oauth_module.OAuthRefused("email_not_verified", "unverified")
        ),
    )
    create_token_spy = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.oauth.crud_user_refresh_token.create_for_user",
        create_token_spy,
    )

    response = client.get(
        "/api/v1/auth/google/callback?code=abc&state=valid", follow_redirects=False
    )

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["oauth_error"] == ["email_not_verified"]
    create_token_spy.assert_not_awaited()
    db_session.rollback.assert_awaited()


def test_callback_never_signs_in_a_superuser(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    _stub_provider(monkeypatch)
    admin = SimpleNamespace(id=uuid.uuid4(), is_active=True, is_superuser=True)
    monkeypatch.setattr(
        oauth_module, "_find_or_create_user", AsyncMock(return_value=admin)
    )
    create_token_spy = AsyncMock()
    monkeypatch.setattr(
        "app.api.routes.oauth.crud_user_refresh_token.create_for_user",
        create_token_spy,
    )

    response = client.get(
        "/api/v1/auth/google/callback?code=abc&state=valid", follow_redirects=False
    )

    query = parse_qs(urlparse(response.headers["location"]).query)
    assert query["oauth_error"] == ["superuser_oauth_disabled"]
    create_token_spy.assert_not_awaited()
