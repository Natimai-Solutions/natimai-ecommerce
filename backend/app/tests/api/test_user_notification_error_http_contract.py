import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.user.crud.notification import (
    crud_notification,
    crud_user_notification,
)
from app.main import app


@pytest.fixture
def current_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, is_active=True)


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace()


@pytest.fixture(autouse=True)
def override_dependencies(
    current_user: SimpleNamespace,
    db_session: SimpleNamespace,
) -> Generator[None, None, None]:
    async def _override_current_user() -> SimpleNamespace:
        return current_user

    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_get_user_notifications_not_owned_returns_error_payload(
    client: TestClient,
) -> None:
    owner_user_id = uuid.uuid4()

    response = client.get(f"/api/v1/notification/users/{owner_user_id}/notifications")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "notification.not_owned",
            "message": "You cannot access another user's notifications",
            "details": {"user_id": str(owner_user_id)},
        }
    }


def test_get_user_notification_missing_link_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    notification_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_user_notification,
        "get_by_user_and_notification",
        AsyncMock(return_value=None),
    )

    response = client.get(
        f"/api/v1/notification/users/{current_user.id}/notifications/{notification_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "notification.not_found",
            "message": f"Notification '{notification_id}' not found",
            "details": {"notification_id": str(notification_id)},
        }
    }


def test_get_user_notification_missing_record_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    notification_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_user_notification,
        "get_by_user_and_notification",
        AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4(), is_read=False)),
    )
    monkeypatch.setattr(
        crud_notification,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("notification missing")),
    )

    response = client.get(
        f"/api/v1/notification/users/{current_user.id}/notifications/{notification_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "notification.not_found",
            "message": f"Notification '{notification_id}' not found",
            "details": {"notification_id": str(notification_id)},
        }
    }


def test_mark_notification_as_read_missing_link_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    notification_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_user_notification,
        "get_by_user_and_notification",
        AsyncMock(return_value=None),
    )

    response = client.patch(
        f"/api/v1/notification/users/{current_user.id}/notifications/{notification_id}/read"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "notification.not_found",
            "message": f"Notification '{notification_id}' not found",
            "details": {"notification_id": str(notification_id)},
        }
    }


def test_delete_user_notification_missing_link_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    notification_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_user_notification,
        "get_by_user_and_notification",
        AsyncMock(return_value=None),
    )

    response = client.delete(
        f"/api/v1/notification/users/{current_user.id}/notifications/{notification_id}"
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "notification.not_found",
            "message": f"Notification '{notification_id}' not found",
            "details": {"notification_id": str(notification_id)},
        }
    }
