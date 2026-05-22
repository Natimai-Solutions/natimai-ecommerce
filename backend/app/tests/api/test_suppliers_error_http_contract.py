from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_superuser
from app.api.routes import suppliers as suppliers_routes
from app.core.db import get_db
from app.main import app


class DummySupplierAdapter:
    def __init__(
        self,
        *,
        name: str,
        display_name: str,
        sync_enabled: bool,
        configured: bool,
        default_categories: list[str] | None = None,
    ) -> None:
        self.name = name
        self.display_name = display_name
        self._sync_enabled = sync_enabled
        self._configured = configured
        self.default_categories = default_categories or []

    def is_sync_enabled(self) -> bool:
        return self._sync_enabled

    def is_configured(self) -> bool:
        return self._configured


@pytest.fixture
def current_superuser() -> SimpleNamespace:
    return SimpleNamespace(id="admin", is_superuser=True, is_active=True)


@pytest.fixture
def db_session() -> SimpleNamespace:
    return SimpleNamespace()


@pytest.fixture(autouse=True)
def override_dependencies(
    current_superuser: SimpleNamespace,
    db_session: SimpleNamespace,
) -> Generator[None, None, None]:
    async def _override_current_superuser() -> SimpleNamespace:
        return current_superuser

    async def _override_get_db() -> AsyncGenerator[SimpleNamespace, None]:
        yield db_session

    app.dependency_overrides[get_current_active_superuser] = _override_current_superuser
    app.dependency_overrides[get_db] = _override_get_db
    yield
    app.dependency_overrides.clear()


def test_get_supplier_unknown_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(suppliers_routes, "has_supplier", lambda _name: False)
    monkeypatch.setattr(
        suppliers_routes,
        "supplier_names",
        lambda: ["ingram_micro", "demo_supplier"],
    )

    response = client.get("/api/v1/suppliers/unknown/config")

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "supplier.not_found",
            "message": "Unknown supplier 'unknown'. Registered: ingram_micro, demo_supplier",
            "details": {
                "supplier_name": "unknown",
                "registered": ["ingram_micro", "demo_supplier"],
            },
        }
    }


def test_trigger_product_sync_disabled_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = DummySupplierAdapter(
        name="demo_supplier",
        display_name="Demo Supplier",
        sync_enabled=False,
        configured=True,
    )

    monkeypatch.setattr(suppliers_routes, "has_supplier", lambda _name: True)
    monkeypatch.setattr(suppliers_routes, "get_adapter", lambda _name: adapter)

    response = client.post("/api/v1/suppliers/demo/sync/products", json={})

    assert response.status_code == 400
    assert response.json() == {
        "error": {
            "code": "supplier.sync.disabled",
            "message": "Demo Supplier synchronization is disabled in settings",
            "details": {"supplier_name": "demo_supplier"},
        }
    }


def test_trigger_inventory_sync_not_configured_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = DummySupplierAdapter(
        name="demo_supplier",
        display_name="Demo Supplier",
        sync_enabled=True,
        configured=False,
    )

    monkeypatch.setattr(suppliers_routes, "has_supplier", lambda _name: True)
    monkeypatch.setattr(suppliers_routes, "get_adapter", lambda _name: adapter)

    response = client.post("/api/v1/suppliers/demo/sync/inventory", json={})

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "supplier.credentials.not_configured",
            "message": "Demo Supplier credentials not configured",
            "details": {"supplier_name": "demo_supplier"},
        }
    }


def test_trigger_inventory_sync_queue_failure_returns_error_payload(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    adapter = DummySupplierAdapter(
        name="demo_supplier",
        display_name="Demo Supplier",
        sync_enabled=True,
        configured=True,
    )

    monkeypatch.setattr(suppliers_routes, "has_supplier", lambda _name: True)
    monkeypatch.setattr(suppliers_routes, "get_adapter", lambda _name: adapter)
    monkeypatch.setattr(
        suppliers_routes,
        "trigger_inventory_refresh",
        AsyncMock(side_effect=RuntimeError("queue down")),
    )

    response = client.post(
        "/api/v1/suppliers/demo/sync/inventory",
        json={"skus": ["SKU-1"]},
    )

    assert response.status_code == 500
    assert response.json() == {
        "error": {
            "code": "supplier.sync.queue_failed",
            "message": "Failed to queue inventory refresh: queue down",
            "details": {
                "supplier_name": "demo_supplier",
                "sync_type": "inventory",
                "reason": "queue down",
            },
        }
    }
