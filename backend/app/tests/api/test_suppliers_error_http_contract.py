from collections.abc import AsyncGenerator, Generator
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_current_active_superuser
from app.api.routes import suppliers as suppliers_routes
from app.core.db import get_db
from app.features.integrations.models.supplier import SupplierKind
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
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
        self.supplier_display_name = display_name
        self._sync_enabled = sync_enabled
        self._configured = configured
        self.default_categories = default_categories or []

    def is_sync_enabled(self) -> bool:
        return self._sync_enabled

    def is_configured(self) -> bool:
        return self._configured


def _supplier_row(code: str = "demo_supplier", **overrides: object) -> SimpleNamespace:
    fields: dict[str, object] = {
        "code": code,
        "name": "Demo Supplier",
        "kind": SupplierKind.API,
        "adapter_key": "demo",
        "is_active": True,
        "sync_enabled": True,
        "is_domestic": False,
        "default_categories": [],
        "column_mapping": None,
        "price_currency": None,
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _install_api_supplier(
    monkeypatch: pytest.MonkeyPatch, adapter: DummySupplierAdapter
) -> None:
    monkeypatch.setattr(
        suppliers_routes, "load_supplier", AsyncMock(return_value=_supplier_row())
    )
    monkeypatch.setattr(suppliers_routes, "has_adapter", lambda _key: True)
    monkeypatch.setattr(suppliers_routes, "adapter_for_supplier", lambda _row: adapter)


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
    monkeypatch.setattr(suppliers_routes, "load_supplier", AsyncMock(return_value=None))
    monkeypatch.setattr(
        suppliers_routes,
        "list_supplier_rows",
        AsyncMock(
            return_value=[
                SimpleNamespace(code="ingram_micro"),
                SimpleNamespace(code="demo_supplier"),
            ]
        ),
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


def test_sync_on_a_manual_supplier_returns_not_api(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A generic (manual) supplier has nothing to synchronize."""
    monkeypatch.setattr(
        suppliers_routes,
        "load_supplier",
        AsyncMock(
            return_value=_supplier_row(
                "generic_fr", kind=SupplierKind.MANUAL, adapter_key=None
            )
        ),
    )

    response = client.post("/api/v1/suppliers/generic_fr/sync/products", json={})

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "supplier.not_api"
    assert body["error"]["details"] == {
        "supplier_name": "generic_fr",
        "kind": "manual",
        "adapter_key": None,
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
    _install_api_supplier(monkeypatch, adapter)

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
    _install_api_supplier(monkeypatch, adapter)

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
    _install_api_supplier(monkeypatch, adapter)
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


def test_import_file_rejects_missing_mapping(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        suppliers_routes,
        "load_supplier",
        AsyncMock(
            return_value=_supplier_row(
                "generic_fr", kind=SupplierKind.FILE, adapter_key=None
            )
        ),
    )

    response = client.post(
        "/api/v1/suppliers/generic_fr/import-file",
        files={"file": ("catalogue.csv", b"ref;nom\nA1;Produit A\n", "text/csv")},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["error"]["code"] == "supplier.import.mapping_invalid"
    assert body["error"]["details"]["headers"] == ["ref", "nom"]


def test_import_file_dry_run_reports_parsed_rows(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        suppliers_routes,
        "load_supplier",
        AsyncMock(
            return_value=_supplier_row(
                "generic_fr",
                kind=SupplierKind.FILE,
                adapter_key=None,
                price_currency="EUR",
                column_mapping={
                    "supplier_sku": "ref",
                    "name": "nom",
                    "price": "prix",
                    "quantity": "stock",
                },
            )
        ),
    )
    content = b"ref;nom;prix;stock\nA1;Produit A;1 234,50;3\nA2;;10;1\n"
    # The resolution step reads the catalog: stubbed, the DB is a namespace here.
    preview = AsyncMock(
        return_value=(
            {"new": 1, "updated": 0, "adopted": 0, "ambiguous": 0, "skipped": 0},
            [
                {
                    "supplier_sku": "A1",
                    "name": "Produit A",
                    "action": "new",
                    "match_key": None,
                    "product_id": None,
                    "product_name": None,
                    "message": None,
                }
            ],
        )
    )
    monkeypatch.setattr(SupplierSyncOrchestrator, "preview_items", preview)

    response = client.post(
        "/api/v1/suppliers/generic_fr/import-file?dry_run=true",
        files={"file": ("catalogue.csv", content, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["dry_run"] is True
    assert body["resolution"]["new"] == 1
    assert body["sample_resolutions"][0]["action"] == "new"
    assert body["parsed_products"] == 1
    assert body["rejected_rows"] == 1
    assert body["row_errors"][0]["row_number"] == 3
    assert body["sample"][0] == {
        "supplier_sku": "A1",
        "name": "Produit A",
        "manufacturer": None,
        "price": "1234.50",
        "currency": "EUR",
        "quantity": "3",
        "category": None,
        "subcategory": None,
    }
