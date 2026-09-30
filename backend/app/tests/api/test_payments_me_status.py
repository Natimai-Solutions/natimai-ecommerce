"""Contract tests for GET /payments/me/{payment_id} (self-service status polling)."""

import uuid
from collections.abc import AsyncGenerator, Generator
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.core.db import get_db
from app.features.base.crud import RecordNotFoundError
from app.features.payment.crud.payment import crud_payment
from app.main import app


@pytest.fixture
def current_user() -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        is_superuser=False,
        is_active=True,
        price_group_id=None,
    )


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


def _payment(*, user_id: uuid.UUID, status_id: uuid.UUID | None) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        user_id=user_id,
        order_id=uuid.uuid4(),
        provider_code="payzen",
        amount=Decimal("1500.00"),
        currency="XPF",
        payment_status_id=status_id,
    )


def test_get_my_payment_status_not_found_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payment_id = uuid.uuid4()
    monkeypatch.setattr(
        crud_payment,
        "read",
        AsyncMock(side_effect=RecordNotFoundError("payment missing")),
    )

    response = client.get(f"/api/v1/payments/me/{payment_id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "payment.not_found"


def test_get_my_payment_status_not_owned_returns_403(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    other_user_id = uuid.uuid4()
    monkeypatch.setattr(
        crud_payment,
        "read",
        AsyncMock(return_value=_payment(user_id=other_user_id, status_id=None)),
    )

    response = client.get(f"/api/v1/payments/me/{uuid.uuid4()}")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "payment.not_owned"


def test_get_my_payment_status_terminal_completed(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
    db_session: SimpleNamespace,
) -> None:
    status_id = uuid.uuid4()
    monkeypatch.setattr(
        crud_payment,
        "read",
        AsyncMock(return_value=_payment(user_id=current_user.id, status_id=status_id)),
    )
    db_session.get = AsyncMock(return_value=SimpleNamespace(name="Completed"))

    response = client.get(f"/api/v1/payments/me/{uuid.uuid4()}")

    assert response.status_code == 200
    body = response.json()
    assert body["status_name"] == "Completed"
    assert body["is_terminal"] is True
    assert body["currency"] == "XPF"


def test_get_my_payment_status_non_terminal_pending(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
    db_session: SimpleNamespace,
) -> None:
    status_id = uuid.uuid4()
    monkeypatch.setattr(
        crud_payment,
        "read",
        AsyncMock(return_value=_payment(user_id=current_user.id, status_id=status_id)),
    )
    db_session.get = AsyncMock(return_value=SimpleNamespace(name="Pending"))

    response = client.get(f"/api/v1/payments/me/{uuid.uuid4()}")

    assert response.status_code == 200
    body = response.json()
    assert body["status_name"] == "Pending"
    assert body["is_terminal"] is False


def test_me_methods_resolves_to_methods_endpoint_not_payment_id(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: /payments/me/methods must hit the methods endpoint, not be
    parsed as a payment_id UUID by the parametrized /me/{payment_id} route."""
    monkeypatch.setattr(
        "app.api.routes.payments.get_eligible_payment_methods",
        AsyncMock(return_value=[]),
    )

    response = client.get("/api/v1/payments/me/methods")

    assert response.status_code == 200
    assert response.json() == []


def test_get_my_payment_status_authorized_is_terminal(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    current_user: SimpleNamespace,
    db_session: SimpleNamespace,
) -> None:
    """Deferred capture: an authorised card is final for the customer, so the
    return page stops polling instead of timing out."""
    status_id = uuid.uuid4()
    monkeypatch.setattr(
        crud_payment,
        "read",
        AsyncMock(return_value=_payment(user_id=current_user.id, status_id=status_id)),
    )
    db_session.get = AsyncMock(return_value=SimpleNamespace(name="Authorized"))

    response = client.get(f"/api/v1/payments/me/{uuid.uuid4()}")

    assert response.status_code == 200
    body = response.json()
    assert body["status_name"] == "Authorized"
    assert body["is_terminal"] is True
