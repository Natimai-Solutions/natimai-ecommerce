import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_current_user_optional
from app.core.db import get_db
from app.features.user.crud.user_group import crud_user_group
from app.main import app


@pytest.fixture
def current_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, is_active=True)


@pytest.fixture
def admin_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)


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

    async def _override_current_user_optional() -> SimpleNamespace:
        return current_user

    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    app.dependency_overrides[get_current_user] = _override_current_user
    app.dependency_overrides[get_current_user_optional] = (
        _override_current_user_optional
    )
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_get_groups_by_type_authentication_required_returns_error_payload(
    client: TestClient,
) -> None:
    async def _override_current_user_optional() -> None:
        return None

    app.dependency_overrides[get_current_user_optional] = (
        _override_current_user_optional
    )

    response = client.get("/api/v1/group/by-type/pricing")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "group.authentication_required",
            "message": "Authentication required",
            "details": {"resource": "group.by_type"},
        }
    }


def test_add_user_to_group_admin_required_returns_error_payload(
    client: TestClient,
) -> None:
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()

    response = client.post(
        f"/api/v1/group/{group_id}/users",
        json={"user_id": str(user_id), "group_id": str(group_id)},
    )

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "group.admin_required",
            "message": "Admin access required",
            "details": {"resource": "group.users.add"},
        }
    }


def test_add_user_to_group_value_error_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    admin_user: SimpleNamespace,
) -> None:
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async def _override_admin_user() -> SimpleNamespace:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_admin_user

    monkeypatch.setattr(
        crud_user_group,
        "add_user_to_group",
        AsyncMock(side_effect=ValueError("User already in group")),
    )

    response = client.post(
        f"/api/v1/group/{group_id}/users",
        json={"user_id": str(user_id), "group_id": str(group_id)},
    )

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "group.user_membership.invalid",
            "message": "User already in group",
            "details": {
                "group_id": str(group_id),
                "user_id": str(user_id),
                "reason": "User already in group",
            },
        }
    }


def test_remove_user_from_group_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    admin_user: SimpleNamespace,
) -> None:
    group_id = uuid.uuid4()
    user_id = uuid.uuid4()

    async def _override_admin_user() -> SimpleNamespace:
        return admin_user

    app.dependency_overrides[get_current_user] = _override_admin_user

    monkeypatch.setattr(
        crud_user_group,
        "remove_user_from_group",
        AsyncMock(return_value=False),
    )

    response = client.delete(f"/api/v1/group/{group_id}/users/{user_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "group.user_not_in_group",
            "message": f"User {user_id} not found in group {group_id}",
            "details": {
                "group_id": str(group_id),
                "user_id": str(user_id),
            },
        }
    }


def test_get_user_groups_not_owned_returns_error_payload(client: TestClient) -> None:
    owner_user_id = uuid.uuid4()

    response = client.get(f"/api/v1/group/users/{owner_user_id}/groups")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "group.not_owned",
            "message": "You cannot access another user's groups",
            "details": {"user_id": str(owner_user_id)},
        }
    }


def test_get_group_security_permissions_admin_required_returns_error_payload(
    client: TestClient,
) -> None:
    group_id = uuid.uuid4()

    response = client.get(f"/api/v1/group_security/group/{group_id}/permissions")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "group_security.admin_required",
            "message": "Admin access required",
            "details": {"resource": "group_security.group_permissions"},
        }
    }


def test_get_group_users_admin_required_returns_error_payload(
    client: TestClient,
) -> None:
    """S4 audit fix: listing a group's members enumerates user ids — admin only."""
    group_id = uuid.uuid4()

    response = client.get(f"/api/v1/group/{group_id}/users")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "group.admin_required",
            "message": "Admin access required",
            "details": {"resource": "group.users.list"},
        }
    }


def test_get_group_users_allows_admin(
    client: TestClient,
    current_user: SimpleNamespace,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    current_user.is_superuser = True
    monkeypatch.setattr(
        crud_user_group,
        "get_group_users",
        AsyncMock(return_value=[]),
    )

    response = client.get(f"/api/v1/group/{uuid.uuid4()}/users")

    assert response.status_code == 200
    assert response.json() == {"data": [], "count": 0}
