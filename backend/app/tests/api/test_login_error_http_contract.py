import uuid
from collections.abc import AsyncGenerator, Generator
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient
from jwt.exceptions import InvalidTokenError

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


def test_login_access_token_invalid_credentials_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(crud_user, "authenticate", AsyncMock(return_value=None))

    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "john@example.com", "password": "wrong"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "login.credentials.invalid",
            "message": "Email ou mot de passe incorrect.",
            "details": {"reason": "invalid_credentials"},
        }
    }


def test_login_access_token_inactive_user_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user = SimpleNamespace(id=uuid.uuid4(), is_active=False)

    monkeypatch.setattr(crud_user, "authenticate", AsyncMock(return_value=user))

    response = client.post(
        "/api/v1/login/access-token",
        data={"username": "john@example.com", "password": "secret"},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "login.user.inactive",
            "message": "Utilisateur désactivé",
            "details": {"user_id": str(user.id)},
        }
    }


def test_refresh_access_token_decode_failure_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        security,
        "decode_token",
        lambda _token: (_ for _ in ()).throw(InvalidTokenError("invalid")),
    )

    response = client.post(
        "/api/v1/login/refresh-token",
        cookies={settings.REFRESH_COOKIE_NAME: "bad-token"},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "login.refresh_token.invalid",
            "message": "Refresh token invalide",
            "details": {"reason": "decode_failed"},
        }
    }


def test_refresh_access_token_missing_session_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    refresh_jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(
        user_id,
        expires_delta=timedelta(days=1),
        jti=refresh_jti,
    )

    monkeypatch.setattr(
        crud_user,
        "read",
        AsyncMock(return_value=SimpleNamespace(id=user_id, is_active=True)),
    )
    monkeypatch.setattr(
        crud_user_refresh_token,
        "get_by_user_and_jti",
        AsyncMock(return_value=None),
    )

    response = client.post(
        "/api/v1/login/refresh-token",
        cookies={settings.REFRESH_COOKIE_NAME: refresh_token},
    )

    assert response.status_code == 401
    assert response.json() == {
        "error": {
            "code": "login.refresh_token.invalid",
            "message": "Refresh token invalide",
            "details": {
                "reason": "session_not_found",
                "user_id": str(user_id),
                "jti": refresh_jti,
            },
        }
    }


def test_refresh_access_token_revoked_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    refresh_jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(
        user_id,
        expires_delta=timedelta(days=1),
        jti=refresh_jti,
    )

    refresh_session = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        jti=refresh_jti,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=1),
        revoked_at=datetime.now(timezone.utc),
    )

    revoke_all_mock = AsyncMock(return_value=1)
    monkeypatch.setattr(
        crud_user,
        "read",
        AsyncMock(return_value=SimpleNamespace(id=user_id, is_active=True)),
    )
    monkeypatch.setattr(
        crud_user_refresh_token,
        "get_by_user_and_jti",
        AsyncMock(return_value=refresh_session),
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
                "jti": refresh_jti,
            },
        }
    }

    assert revoke_all_mock.await_args is not None
    revoke_all_kwargs = revoke_all_mock.await_args.kwargs
    assert revoke_all_kwargs["user_id"] == user_id
    assert revoke_all_kwargs["reason"] == "reuse_detected"


def test_refresh_access_token_expired_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = uuid.uuid4()
    refresh_jti = str(uuid.uuid4())
    refresh_token = security.create_refresh_token(
        user_id,
        expires_delta=timedelta(days=1),
        jti=refresh_jti,
    )

    user = SimpleNamespace(id=user_id, is_active=True)
    refresh_session = SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        jti=refresh_jti,
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
        revoked_at=None,
    )

    revoke_mock = AsyncMock(return_value=refresh_session)
    monkeypatch.setattr(crud_user, "read", AsyncMock(return_value=user))
    monkeypatch.setattr(
        crud_user_refresh_token,
        "get_by_user_and_jti",
        AsyncMock(return_value=refresh_session),
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
                "jti": refresh_jti,
            },
        }
    }

    assert revoke_mock.await_args is not None
    revoke_kwargs = revoke_mock.await_args.kwargs
    assert revoke_kwargs["token"] is refresh_session
    assert revoke_kwargs["reason"] == "expired"
