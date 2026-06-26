import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.core import security
from app.core.config import settings
from app.core.db import get_db
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.crud.user import crud_user
from app.main import app


@pytest.fixture(autouse=True)
def override_db_dependency() -> Generator[None, None, None]:
    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield SimpleNamespace()

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_access_token_persists_refresh_session(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    user = SimpleNamespace(id=user_id, is_active=True)

    authenticate_mock = AsyncMock(return_value=user)
    persist_refresh_mock = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))

    monkeypatch.setattr(crud_user, "authenticate", authenticate_mock)
    monkeypatch.setattr(
        crud_user_refresh_token,
        "create_for_user",
        persist_refresh_mock,
    )

    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "john@example.com", "password": "secret"},
    )

    assert response.status_code == 200
    # Refresh token is delivered as an HttpOnly cookie, never in the body.
    assert "refresh_token" not in response.json()
    refresh_cookie = response.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert refresh_cookie is not None

    refresh_payload = security.decode_token(refresh_cookie)
    assert refresh_payload["type"] == "refresh"
    assert refresh_payload["sub"] == str(user_id)
    assert refresh_payload["jti"]

    assert persist_refresh_mock.await_args is not None
    persist_kwargs = persist_refresh_mock.await_args.kwargs
    assert persist_kwargs["user_id"] == user_id
    assert persist_kwargs["jti"] == refresh_payload["jti"]
    assert persist_kwargs["user"] is user


@pytest.mark.asyncio
async def test_refresh_token_rotates_and_returns_new_pair(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    old_jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(
        user_id,
        expires_delta=timedelta(days=1),
        jti=old_jti,
    )

    user = SimpleNamespace(id=user_id, is_active=True)
    refresh_session = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        jti=old_jti,
        # Naive UTC, mirroring the tz-less DB column (regression: comparing this
        # to an aware `now` used to raise TypeError).
        expires_at=(datetime.now(timezone.utc) + timedelta(hours=1)).replace(
            tzinfo=None
        ),
        revoked_at=None,
    )

    read_user_mock = AsyncMock(return_value=user)
    get_refresh_mock = AsyncMock(return_value=refresh_session)
    rotate_mock = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))

    monkeypatch.setattr(crud_user, "read", read_user_mock)
    monkeypatch.setattr(
        crud_user_refresh_token,
        "get_by_user_and_jti",
        get_refresh_mock,
    )
    monkeypatch.setattr(crud_user_refresh_token, "rotate_token", rotate_mock)

    response = client.post(
        "/api/v1/login/refresh-token",
        cookies={settings.REFRESH_COOKIE_NAME: refresh_token},
    )

    assert response.status_code == 200
    new_refresh_cookie = response.cookies.get(settings.REFRESH_COOKIE_NAME)
    assert new_refresh_cookie is not None

    new_refresh_payload = security.decode_token(new_refresh_cookie)
    assert new_refresh_payload["type"] == "refresh"
    assert new_refresh_payload["sub"] == str(user_id)
    assert new_refresh_payload["jti"] != old_jti

    assert rotate_mock.await_args is not None
    rotate_kwargs = rotate_mock.await_args.kwargs
    assert rotate_kwargs["current_token"] is refresh_session
    assert rotate_kwargs["new_jti"] == new_refresh_payload["jti"]
    assert rotate_kwargs["user"] is user


@pytest.mark.asyncio
async def test_refresh_token_expired_is_revoked_and_rejected(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    old_jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(
        user_id,
        expires_delta=timedelta(days=1),
        jti=old_jti,
    )

    user = SimpleNamespace(id=user_id, is_active=True)
    refresh_session = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        jti=old_jti,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        revoked_at=None,
    )

    read_user_mock = AsyncMock(return_value=user)
    get_refresh_mock = AsyncMock(return_value=refresh_session)
    revoke_mock = AsyncMock(return_value=refresh_session)

    monkeypatch.setattr(crud_user, "read", read_user_mock)
    monkeypatch.setattr(
        crud_user_refresh_token,
        "get_by_user_and_jti",
        get_refresh_mock,
    )
    monkeypatch.setattr(crud_user_refresh_token, "revoke_token", revoke_mock)

    response = client.post(
        "/api/v1/login/refresh-token",
        cookies={settings.REFRESH_COOKIE_NAME: refresh_token},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "login.refresh_token.expired",
            "message": "Refresh token expiré",
            "details": {
                "user_id": str(user_id),
                "jti": old_jti,
            },
        }
    }

    assert revoke_mock.await_args is not None
    revoke_kwargs = revoke_mock.await_args.kwargs
    assert revoke_kwargs["token"] is refresh_session
    assert revoke_kwargs["reason"] == "expired"


@pytest.mark.asyncio
async def test_refresh_token_reuse_revokes_all_active_sessions(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    old_jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(
        user_id,
        expires_delta=timedelta(days=1),
        jti=old_jti,
    )

    user = SimpleNamespace(id=user_id, is_active=True)
    refresh_session = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        jti=old_jti,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        revoked_at=datetime.now(timezone.utc),
    )

    read_user_mock = AsyncMock(return_value=user)
    get_refresh_mock = AsyncMock(return_value=refresh_session)
    revoke_all_mock = AsyncMock(return_value=2)

    monkeypatch.setattr(crud_user, "read", read_user_mock)
    monkeypatch.setattr(
        crud_user_refresh_token,
        "get_by_user_and_jti",
        get_refresh_mock,
    )
    monkeypatch.setattr(
        crud_user_refresh_token,
        "revoke_all_active_for_user",
        revoke_all_mock,
    )

    response = client.post(
        "/api/v1/login/refresh-token",
        cookies={settings.REFRESH_COOKIE_NAME: refresh_token},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "login.refresh_token.revoked",
            "message": "Refresh token révoqué",
            "details": {
                "user_id": str(user_id),
                "jti": old_jti,
            },
        }
    }

    assert revoke_all_mock.await_args is not None
    revoke_all_kwargs = revoke_all_mock.await_args.kwargs
    assert revoke_all_kwargs["user_id"] == user_id
    assert revoke_all_kwargs["reason"] == "reuse_detected"


@pytest.mark.asyncio
async def test_logout_revokes_session_and_clears_cookie(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(
        user_id, expires_delta=timedelta(days=1), jti=jti
    )
    session_row = SimpleNamespace(
        id=uuid.uuid4(), user_id=user_id, jti=jti, revoked_at=None
    )
    get_mock = AsyncMock(return_value=session_row)
    revoke_mock = AsyncMock(return_value=session_row)
    monkeypatch.setattr(crud_user_refresh_token, "get_by_user_and_jti", get_mock)
    monkeypatch.setattr(crud_user_refresh_token, "revoke_token", revoke_mock)

    response = client.post(
        "/api/v1/login/logout",
        cookies={settings.REFRESH_COOKIE_NAME: refresh_token},
    )

    assert response.status_code == 204
    revoke_mock.assert_awaited_once()
    assert revoke_mock.await_args is not None
    assert revoke_mock.await_args.kwargs["reason"] == "logout"
    # The cookie is cleared on the way out.
    assert settings.REFRESH_COOKIE_NAME in response.headers.get("set-cookie", "")


def test_logout_without_cookie_is_idempotent(client: TestClient) -> None:
    response = client.post("/api/v1/login/logout")
    assert response.status_code == 204
