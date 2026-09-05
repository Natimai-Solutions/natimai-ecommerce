"""Unit tests for the orchestrator's mapping of supplier payloads (no DB)."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest

from app.features.integrations.crud.supplier_sync import supplier_product_mapping_crud
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.place.crud import crud_place
from app.features.product.crud.product import crud_product
from app.features.product.models.product import PricingMode
from app.services.suppliers.base import NormalizedProductData


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _adapter(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "name": "generic_fr",
        "origin_place_id": None,
        "origin_place_code": None,
        "is_domestic": False,
        "price_currency": None,
        "default_categories": [],
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _item(**overrides: Any) -> NormalizedProductData:
    fields: dict[str, Any] = {"supplier_sku": "SKU-1", "name": "Produit"}
    fields.update(overrides)
    return NormalizedProductData(**fields)


# ---------------------------------------------------------------------------
# _to_product_data
# ---------------------------------------------------------------------------


def test_catalog_payload_without_price_leaves_cost_and_stock_alone() -> None:
    """Ingram's catalog endpoint carries neither: zeroing them each sweep blanked the shop."""
    data = SupplierSyncOrchestrator(_adapter())._to_product_data(_item())

    for key in (
        "cost_amount",
        "supplier_price",
        "supplier_quantity",
        "last_supplier_sync",
    ):
        assert key not in data
    assert data["supplier_name"] == "generic_fr"
    assert data["is_supplier_managed"] is True


def test_payload_with_price_and_stock_is_applied_like_an_inventory_refresh() -> None:
    data = SupplierSyncOrchestrator(_adapter(price_currency="EUR"))._to_product_data(
        _item(price=Decimal("1234.50"), quantity=Decimal("3"))
    )

    assert data["cost_amount"] == Decimal("1234.50")
    assert data["cost_currency"] == "EUR"
    assert data["supplier_price"] == Decimal("1234.50")
    assert data["supplier_price_currency"] == "EUR"
    assert data["supplier_quantity"] == Decimal("3")
    assert data["supplier_missing_since"] is None
    assert data["last_supplier_sync"] is not None


def test_item_currency_wins_over_the_supplier_default() -> None:
    data = SupplierSyncOrchestrator(_adapter(price_currency="EUR"))._to_product_data(
        _item(price=10, currency="USD")
    )

    assert data["cost_currency"] == "USD"


def test_quantity_alone_does_not_touch_the_cost() -> None:
    data = SupplierSyncOrchestrator(_adapter())._to_product_data(_item(quantity=7))

    assert data["supplier_quantity"] == Decimal("7")
    assert "cost_amount" not in data


# ---------------------------------------------------------------------------
# upsert_product: origin and pricing mode stamping
# ---------------------------------------------------------------------------


def _install_crud(monkeypatch: pytest.MonkeyPatch, *, existing: Any) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def _create(session: Any, *, data: Any, user: Any) -> Any:
        del session, user
        captured["create"] = data.model_dump(exclude_unset=True)
        return SimpleNamespace(id=uuid.uuid4())

    async def _update(
        session: Any, *, id: Any, data: Any, user: Any, record: Any
    ) -> Any:
        del session, id, user
        captured["update"] = data.model_dump(exclude_unset=True)
        return record

    monkeypatch.setattr(
        supplier_product_mapping_crud,
        "get_by_supplier_sku",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        crud_product, "get_by_supplier_sku", AsyncMock(return_value=existing)
    )
    monkeypatch.setattr(crud_product, "create_draft", _create)
    monkeypatch.setattr(crud_product, "update_draft", _update)
    monkeypatch.setattr(crud_place, "get_by_code", AsyncMock(return_value=None))
    return captured


@pytest.mark.anyio
async def test_domestic_supplier_creates_domestic_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = uuid.uuid4()
    captured = _install_crud(monkeypatch, existing=None)
    orchestrator = SupplierSyncOrchestrator(
        _adapter(is_domestic=True, origin_place_id=origin)
    )

    result = await orchestrator.upsert_product(AsyncMock(), _item())

    assert result["action"] == "created"
    assert captured["create"]["pricing_mode"] == PricingMode.DOMESTIC
    assert captured["create"]["supplier_place_id"] == origin


@pytest.mark.anyio
async def test_import_supplier_creates_import_products(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = _install_crud(monkeypatch, existing=None)

    await SupplierSyncOrchestrator(_adapter()).upsert_product(AsyncMock(), _item())

    assert captured["create"]["pricing_mode"] == PricingMode.IMPORT


@pytest.mark.anyio
async def test_existing_products_keep_their_pricing_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An admin may have re-priced the product as fixed: the sync must not undo it."""
    existing = SimpleNamespace(
        id=uuid.uuid4(),
        is_supplier_managed=True,
        supplier_name="generic_fr",
        supplier_sku="SKU-1",
        supplier_place_id=uuid.uuid4(),
        overridden_fields=["name"],
    )
    captured = _install_crud(monkeypatch, existing=existing)

    result = await SupplierSyncOrchestrator(_adapter(is_domestic=True)).upsert_product(
        AsyncMock(), _item(name="Nouveau nom")
    )

    assert result["action"] == "updated"
    assert "pricing_mode" not in captured["update"]
    assert "supplier_place_id" not in captured["update"]
    # The locked field is respected.
    assert "name" not in captured["update"]


@pytest.mark.anyio
async def test_origin_place_id_wins_over_the_code_lookup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    origin = uuid.uuid4()
    _install_crud(monkeypatch, existing=None)
    lookup = AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4()))
    monkeypatch.setattr(crud_place, "get_by_code", lookup)
    orchestrator = SupplierSyncOrchestrator(
        _adapter(origin_place_id=origin, origin_place_code="FR_SUPPLIERS")
    )

    assert await orchestrator._resolve_origin_place_id(AsyncMock()) == origin
    lookup.assert_not_awaited()


# ---------------------------------------------------------------------------
# sync_items
# ---------------------------------------------------------------------------


@pytest.mark.anyio
async def test_sync_items_counts_and_isolates_failures(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = SupplierSyncOrchestrator(_adapter())
    outcomes: Iterator[Any] = iter(
        [
            {"action": "created", "product_id": "1"},
            RuntimeError("boom"),
            {"action": "updated", "product_id": "2"},
            {"action": "filtered", "product_id": ""},
        ]
    )

    async def _upsert(_session: Any, _item: Any) -> dict[str, str]:
        outcome = next(outcomes)
        if isinstance(outcome, Exception):
            raise outcome
        return cast(dict[str, str], outcome)

    monkeypatch.setattr(orchestrator, "upsert_product", _upsert)
    session = AsyncMock()
    errors: list[dict[str, str]] = []

    stats = await orchestrator.sync_items(
        session,
        [
            _item(supplier_sku="A"),
            _item(supplier_sku="B"),
            _item(supplier_sku="C"),
            _item(supplier_sku="D"),
            _item(supplier_sku="", name="sans ref"),
        ],
        errors=errors,
    )

    assert stats == {
        "total_fetched": 5,
        "new_products": 1,
        "updated_products": 1,
        "skipped_products": 1,
        "filtered_products": 1,
        "errors": 1,
    }
    assert errors == [{"sku": "B", "error": "boom"}]
    assert session.commit.await_count == 2
    assert session.rollback.await_count == 1
