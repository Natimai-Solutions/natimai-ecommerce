"""Contract tests for the customer-facing GET /orders/me listing.

A user only ever sees their own orders — ownership is derived from the JWT, so
the CRUD layer is always queried with the authenticated user's id.
"""

import uuid
from collections.abc import AsyncGenerator, Generator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.db import get_db
from app.features.order.crud.order_crud import crud_order
from app.features.order.models.order import Order
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


def _order(*, user_id: uuid.UUID) -> Order:
    return Order(
        id=uuid.uuid4(),
        user_id=user_id,
        order_status_id=uuid.uuid4(),
        total_amount=Decimal("12990.00"),
    )


def test_list_my_orders_queries_current_user_only(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    orders = [_order(user_id=current_user.id), _order(user_id=current_user.id)]
    get_by_user = AsyncMock(return_value=orders)
    monkeypatch.setattr(crud_order, "get_by_user", get_by_user)

    response = client.get("/api/v1/orders/me")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 2
    assert {item["user_id"] for item in body} == {str(current_user.id)}
    # Ownership is enforced server-side: the listing is always scoped to the JWT user.
    assert get_by_user.call_args.kwargs["user_id"] == current_user.id


def test_list_my_orders_empty(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(crud_order, "get_by_user", AsyncMock(return_value=[]))

    response = client.get("/api/v1/orders/me")

    assert response.status_code == 200
    assert response.json() == []
