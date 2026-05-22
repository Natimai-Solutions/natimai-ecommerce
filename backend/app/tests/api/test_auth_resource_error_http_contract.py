import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_current_user_optional
from app.core.db import get_db
from app.main import app


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace(exec=AsyncMock(return_value=SimpleNamespace(all=lambda: [])))


@pytest.fixture(autouse=True)
def override_db_dependency(
    db_session: SimpleNamespace,
) -> Generator[None, None, None]:
    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_auth_credentials_invalid_returns_error_payload(
    client: TestClient,
) -> None:
    user_id = uuid.uuid4()

    response = client.get(
        f"/api/v1/address/users/{user_id}/addresses",
        headers={"Authorization": "Bearer not-a-valid-token"},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "auth.credentials.invalid",
            "message": "Could not validate credentials",
            "details": {"reason": "invalid_or_malformed_token"},
        }
    }


def test_auth_superuser_required_returns_error_payload(
    client: TestClient,
) -> None:
    async def _override_current_user() -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, is_active=True)

    app.dependency_overrides[get_current_user] = _override_current_user
    try:
        response = client.get("/api/v1/admin/currency-rates")
    finally:
        app.dependency_overrides.pop(get_current_user, None)

    assert response.status_code == 403
    payload = response.json()["error"]
    assert payload["code"] == "auth.superuser.required"
    assert payload["message"] == "The user doesn't have enough privileges"
    assert "user_id" in payload["details"]


def test_resource_authentication_required_returns_error_payload(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/address/")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "resource.authentication_required",
            "message": "Authentication required on Address",
            "details": {"resource": "address", "permission": "read"},
        }
    }


def test_resource_filter_unsupported_returns_error_payload(
    client: TestClient,
) -> None:
    async def _override_current_user_optional() -> SimpleNamespace:
        return SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)

    app.dependency_overrides[get_current_user_optional] = (
        _override_current_user_optional
    )
    try:
        response = client.get("/api/v1/address/?filter=id%20is%20not%20null")
    finally:
        app.dependency_overrides.pop(get_current_user_optional, None)

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "resource.filter.unsupported",
            "message": "Raw string filters are not supported on this endpoint",
            "details": {
                "resource": "address",
                "filter": "id is not null",
            },
        }
    }
