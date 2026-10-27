import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user, get_current_user_optional
from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import crud_order
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
    async def _override_current_user_optional() -> SimpleNamespace:
        return current_user

    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    app.dependency_overrides[get_current_user] = _override_current_user_optional
    app.dependency_overrides[get_current_user_optional] = (
        _override_current_user_optional
    )
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_order_update_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    order_id = uuid.uuid4()
    # Order writes are superuser-only since the gating pass.
    current_user.is_superuser = True

    monkeypatch.setattr(
        crud_order,
        "update",
        AsyncMock(side_effect=RecordNotFoundError("order missing")),
    )

    response = client.put(f"/api/v1/order/{order_id}", json={})

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "order.not_found",
            "message": f"Order '{order_id}' not found",
            "details": {"order_id": str(order_id)},
        }
    }


def test_order_delete_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    order_id = uuid.uuid4()
    current_user.is_superuser = True

    monkeypatch.setattr(
        crud_order,
        "delete",
        AsyncMock(side_effect=RecordNotFoundError("order missing")),
    )

    response = client.delete(f"/api/v1/order/{order_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "order.not_found",
            "message": f"Order '{order_id}' not found",
            "details": {"order_id": str(order_id)},
        }
    }


def test_get_user_orders_not_owned_returns_error_payload(client: TestClient) -> None:
    owner_user_id = uuid.uuid4()

    response = client.get(f"/api/v1/order/user/{owner_user_id}")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "order.not_found",
            "message": "Commande introuvable",
            "details": {"user_id": str(owner_user_id)},
        }
    }


def test_get_orders_by_status_admin_required_returns_error_payload(
    client: TestClient,
) -> None:
    status_id = uuid.uuid4()

    response = client.get(f"/api/v1/order/status/{status_id}")

    assert response.status_code == 403
    assert response.json() == {
        "error": {
            "code": "order.admin_required",
            "message": "Admin privileges required to access orders by status",
            "details": {"resource": "order.status"},
        }
    }
