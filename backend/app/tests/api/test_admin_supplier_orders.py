"""Contract tests for the /admin/supplier-orders endpoints."""

import uuid
from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_supplier_orders as routes
from app.api.deps import get_current_active_superuser
from app.core.db import get_db
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.main import app


@pytest.fixture
def superuser() -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_superuser=True, is_active=True)


@pytest.fixture
def db_session() -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock(return_value=None)
    session.exec = AsyncMock()
    session.refresh = AsyncMock()
    return session


@pytest.fixture(autouse=True)
def override_dependencies(
    superuser: SimpleNamespace,
    db_session: MagicMock,
) -> Generator[None, None, None]:
    async def _override_superuser() -> SimpleNamespace:
        return superuser

    async def _override_get_db() -> AsyncGenerator[MagicMock, None]:
        yield db_session

    app.dependency_overrides[get_current_active_superuser] = _override_superuser
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def _record(
    status: SupplierOrderStatus,
    *,
    supplier_order_number: str | None = None,
    error_message: str | None = None,
) -> SupplierOrder:
    return SupplierOrder(
        supplier_name="ingram_micro",
        local_order_id=uuid.uuid4(),
        customer_order_number="abc123",
        status=status,
        supplier_order_number=supplier_order_number,
        error_message=error_message,
    )


def test_list_supplier_orders_returns_paginated_payload(
    client: TestClient,
    db_session: MagicMock,
) -> None:
    record = _record(SupplierOrderStatus.SUBMITTED, supplier_order_number="IM-1")
    count_result = MagicMock()
    count_result.one.return_value = 1
    list_result = MagicMock()
    list_result.all.return_value = [record]
    db_session.exec = AsyncMock(side_effect=[count_result, list_result])

    response = client.get("/api/v1/admin/supplier-orders")

    assert response.status_code == 200
    body = response.json()
    assert body["count"] == 1
    assert body["data"][0]["supplier_order_number"] == "IM-1"
    assert body["data"][0]["status"] == "submitted"


def test_list_supplier_orders_accepts_status_filter(
    client: TestClient,
    db_session: MagicMock,
) -> None:
    count_result = MagicMock()
    count_result.one.return_value = 0
    list_result = MagicMock()
    list_result.all.return_value = []
    db_session.exec = AsyncMock(side_effect=[count_result, list_result])

    response = client.get(
        "/api/v1/admin/supplier-orders",
        params={"status": "error", "supplier_name": "ingram_micro"},
    )

    assert response.status_code == 200
    assert response.json()["count"] == 0


def test_get_supplier_order_not_found(client: TestClient) -> None:
    response = client.get(f"/api/v1/admin/supplier-orders/{uuid.uuid4()}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "supplier_order.not_found"


def test_retry_already_submitted_is_noop(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    submitted = _record(SupplierOrderStatus.SUBMITTED, supplier_order_number="IM-7")
    db_session.get = AsyncMock(return_value=submitted)
    process_spy = AsyncMock()
    monkeypatch.setattr(routes, "process_supplier_purchase_order", process_spy)

    response = client.post(f"/api/v1/admin/supplier-orders/{uuid.uuid4()}/retry")

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    process_spy.assert_not_awaited()


def test_retry_error_order_reprocesses(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    errored = _record(SupplierOrderStatus.ERROR, error_message="ship_to missing")
    db_session.get = AsyncMock(return_value=errored)

    submitted = _record(SupplierOrderStatus.SUBMITTED, supplier_order_number="IM-NEW")
    monkeypatch.setattr(
        routes,
        "process_supplier_purchase_order",
        AsyncMock(return_value=submitted),
    )

    response = client.post(f"/api/v1/admin/supplier-orders/{uuid.uuid4()}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["supplier_order_number"] == "IM-NEW"


def test_retry_surfaces_persisted_error_record(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    db_session: MagicMock,
) -> None:
    errored = _record(SupplierOrderStatus.ERROR, error_message="old error")
    db_session.get = AsyncMock(return_value=errored)

    still_error = _record(SupplierOrderStatus.ERROR, error_message="ingram 503")
    monkeypatch.setattr(
        routes,
        "process_supplier_purchase_order",
        AsyncMock(return_value=still_error),
    )

    response = client.post(f"/api/v1/admin/supplier-orders/{uuid.uuid4()}/retry")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["error_message"] == "ingram 503"
