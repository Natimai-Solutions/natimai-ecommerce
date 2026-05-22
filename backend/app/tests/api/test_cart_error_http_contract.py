import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.config import settings
from app.core.db import get_db
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.main import app


@pytest.fixture
def current_user() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=False, is_active=True)


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace(get=AsyncMock(return_value=None))


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


def test_add_cart_item_product_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    cart_id = uuid.uuid4()
    product_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_cart,
        "get_or_create_active_cart",
        AsyncMock(
            return_value=SimpleNamespace(
                id=cart_id,
                user_id=current_user.id,
                currency="XPF",
                total_amount=0,
                is_checked_out=False,
            )
        ),
    )

    response = client.post(
        "/api/v1/cart/items",
        json={"product_id": str(product_id), "quantity": 1},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "cart.product.not_found",
            "message": f"Product '{product_id}' not found",
            "details": {"product_id": str(product_id)},
        }
    }


def test_update_cart_item_quantity_item_missing_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    item_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_cart_item,
        "get_active_item_for_user",
        AsyncMock(return_value=None),
    )

    response = client.patch(
        f"/api/v1/cart/items/{item_id}",
        json={"quantity": 2},
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "cart.item.not_found",
            "message": f"Cart item '{item_id}' not found",
            "details": {"item_id": str(item_id)},
        }
    }


def test_quote_request_support_email_missing_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "")

    response = client.post("/api/v1/cart/quote-request", json={})

    assert response.status_code == 503
    assert response.json() == {
        "error": {
            "code": "cart.quote.unavailable",
            "message": "EMAIL_SUPPORT is not configured",
            "details": {"setting": "EMAIL_SUPPORT"},
        }
    }


def test_quote_request_no_active_cart_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "support@example.com")
    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=None),
    )

    response = client.post("/api/v1/cart/quote-request", json={})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "cart.active.not_found",
            "message": "No active cart found",
            "details": {"user_id": str(current_user.id)},
        }
    }


def test_quote_request_empty_cart_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cart_id = uuid.uuid4()

    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "support@example.com")
    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=SimpleNamespace(id=cart_id)),
    )
    monkeypatch.setattr(
        crud_cart_item,
        "get_by_cart_id",
        AsyncMock(return_value=[]),
    )

    response = client.post("/api/v1/cart/quote-request", json={})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "cart.empty",
            "message": "Cart is empty",
            "details": {"cart_id": str(cart_id)},
        }
    }


def test_checkout_no_active_cart_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
) -> None:
    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=None),
    )

    response = client.post("/api/v1/cart/checkout", json={})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "cart.active.not_found",
            "message": "No active cart found",
            "details": {"user_id": str(current_user.id)},
        }
    }


def test_checkout_empty_cart_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cart_id = uuid.uuid4()

    monkeypatch.setattr(
        crud_cart,
        "get_active_cart_by_user",
        AsyncMock(return_value=SimpleNamespace(id=cart_id)),
    )
    monkeypatch.setattr(
        crud_cart_item,
        "get_by_cart_id",
        AsyncMock(return_value=[]),
    )

    response = client.post("/api/v1/cart/checkout", json={})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "cart.empty",
            "message": "Cart is empty",
            "details": {"cart_id": str(cart_id)},
        }
    }
