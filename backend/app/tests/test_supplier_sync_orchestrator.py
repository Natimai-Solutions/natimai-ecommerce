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
        crud_product,
        "list_by_supplier_sku",
        AsyncMock(return_value=[existing] if existing is not None else []),
    )
    monkeypatch.setattr(
        crud_product, "find_by_identity", AsyncMock(return_value=([], None))
    )
    monkeypatch.setattr(
        supplier_product_mapping_crud, "get_by_product", AsyncMock(return_value=None)
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

    assert stats["total_fetched"] == 5
    assert stats["new_products"] == 1
    assert stats["updated_products"] == 1
    assert stats["skipped_products"] == 1
    assert stats["filtered_products"] == 1
    assert stats["errors"] == 1
    assert errors == [{"sku": "B", "error": "boom"}]
    assert session.commit.await_count == 2
    assert session.rollback.await_count == 1


# ---------------------------------------------------------------------------
# _resolve_existing_product: identity keys within the supplier
# ---------------------------------------------------------------------------


def _existing(**overrides: Any) -> Any:
    fields: dict[str, Any] = {
        "id": uuid.uuid4(),
        "is_supplier_managed": True,
        "supplier_name": "generic_fr",
        "supplier_sku": "OLD-REF",
        "supplier_place_id": uuid.uuid4(),
        "overridden_fields": None,
        "name": "Existant",
    }
    fields.update(overrides)
    return SimpleNamespace(**fields)


def _wire_resolution(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mapping: Any = None,
    by_sku: list[Any] | None = None,
    by_identity: tuple[list[Any], str | None] = ([], None),
) -> dict[str, AsyncMock]:
    mocks = {
        "identity": AsyncMock(return_value=by_identity),
        "by_product": AsyncMock(return_value=None),
    }
    monkeypatch.setattr(
        supplier_product_mapping_crud,
        "get_by_supplier_sku",
        AsyncMock(return_value=mapping),
    )
    monkeypatch.setattr(
        supplier_product_mapping_crud, "get_by_product", mocks["by_product"]
    )
    monkeypatch.setattr(
        crud_product, "list_by_supplier_sku", AsyncMock(return_value=by_sku or [])
    )
    monkeypatch.setattr(crud_product, "find_by_identity", mocks["identity"])
    return mocks


@pytest.mark.anyio
async def test_same_sku_prefers_the_synced_product_over_a_manual_duplicate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    synced = _existing(is_supplier_managed=True)
    manual = _existing(is_supplier_managed=False)
    _wire_resolution(monkeypatch, by_sku=[manual, synced])

    resolution = await SupplierSyncOrchestrator(_adapter())._resolve_existing_product(
        AsyncMock(), _item(supplier_sku="OLD-REF")
    )

    assert resolution.product is synced
    assert resolution.match_key == "supplier_sku"
    assert resolution.ambiguous is False


@pytest.mark.anyio
async def test_two_synced_products_with_the_same_sku_are_ambiguous(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_resolution(monkeypatch, by_sku=[_existing(), _existing()])

    resolution = await SupplierSyncOrchestrator(_adapter())._resolve_existing_product(
        AsyncMock(), _item()
    )

    assert resolution.ambiguous is True
    assert resolution.product is None
    assert len(resolution.candidates) == 2


@pytest.mark.anyio
async def test_barcode_recognises_a_product_under_a_new_reference(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _existing(supplier_sku="OLD-REF")
    mocks = _wire_resolution(monkeypatch, by_identity=([existing], "gtin"))

    resolution = await SupplierSyncOrchestrator(_adapter())._resolve_existing_product(
        AsyncMock(), _item(supplier_sku="NEW-REF", ean="3663970012345")
    )

    assert resolution.product is existing
    assert resolution.match_key == "gtin"
    assert mocks["identity"].await_args is not None
    identity_kwargs = mocks["identity"].await_args.kwargs
    assert identity_kwargs["supplier_name"] == "generic_fr"
    assert identity_kwargs["ean"] == "3663970012345"


@pytest.mark.anyio
async def test_ambiguous_identity_is_reported_and_never_written(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wire_resolution(
        monkeypatch,
        by_identity=([_existing(), _existing()], "manufacturer_part"),
    )
    create = AsyncMock()
    update = AsyncMock()
    monkeypatch.setattr(crud_product, "create_draft", create)
    monkeypatch.setattr(crud_product, "update_draft", update)
    monkeypatch.setattr(crud_place, "get_by_code", AsyncMock(return_value=None))

    result = await SupplierSyncOrchestrator(_adapter()).upsert_product(
        AsyncMock(), _item(manufacturer="ACME", vendor_part_number="X1")
    )

    assert result["action"] == "ambiguous"
    assert result["match_key"] == "manufacturer_part"
    assert "manufacturer_part" in result["error"]
    create.assert_not_awaited()
    update.assert_not_awaited()


@pytest.mark.anyio
async def test_new_reference_rekeys_the_existing_mapping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Recognised by barcode under a new SKU: the mapping row is re-keyed, not doubled."""
    existing = _existing(supplier_sku="OLD-REF")
    mocks = _wire_resolution(monkeypatch, by_identity=([existing], "gtin"))
    old_mapping = SimpleNamespace(
        supplier_sku="OLD-REF", local_product_id=existing.id, sync_enabled=False
    )
    mocks["by_product"].return_value = old_mapping
    captured: dict[str, Any] = {}

    async def _update(
        session: Any, *, id: Any, data: Any, user: Any, record: Any
    ) -> Any:
        del session, id, user
        captured["update"] = data.model_dump(exclude_unset=True)
        return record

    monkeypatch.setattr(crud_product, "update_draft", _update)
    monkeypatch.setattr(crud_place, "get_by_code", AsyncMock(return_value=None))
    session = AsyncMock()

    result = await SupplierSyncOrchestrator(_adapter()).upsert_product(
        session, _item(supplier_sku="NEW-REF", ean="3663970012345")
    )

    assert result["action"] == "updated"
    assert result["match_key"] == "gtin"
    assert captured["update"]["supplier_sku"] == "NEW-REF"
    assert old_mapping.supplier_sku == "NEW-REF"
    assert old_mapping.sync_enabled is True
    session.add.assert_not_called()  # no second mapping row


@pytest.mark.anyio
async def test_sync_items_counts_ambiguous_and_adopted_rows(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = SupplierSyncOrchestrator(_adapter())
    outcomes: Iterator[Any] = iter(
        [
            {"action": "created", "product_id": "1", "match_key": ""},
            {"action": "adopted", "product_id": "2", "match_key": "supplier_sku"},
            {
                "action": "ambiguous",
                "product_id": "",
                "match_key": "gtin",
                "error": "x",
            },
            {"action": "updated", "product_id": "3", "match_key": "gtin"},
        ]
    )

    async def _upsert(_session: Any, _item: Any) -> dict[str, str]:
        return cast(dict[str, str], next(outcomes))

    monkeypatch.setattr(orchestrator, "upsert_product", _upsert)
    session = AsyncMock()
    errors: list[dict[str, str]] = []

    stats = await orchestrator.sync_items(
        session, [_item(supplier_sku=s) for s in "ABCD"], errors=errors
    )

    assert stats["new_products"] == 1
    assert stats["adopted_products"] == 1
    assert stats["ambiguous_products"] == 1
    assert stats["updated_products"] == 1
    assert stats["matched_by_supplier_sku"] == 1
    assert stats["matched_by_gtin"] == 1
    assert errors == [{"sku": "C", "error": "x"}]
    assert session.commit.await_count == 3


@pytest.mark.anyio
async def test_preview_items_resolves_without_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    existing = _existing(name="Déjà là")
    manual = _existing(is_supplier_managed=False, name="Saisi", supplier_sku="M-1")
    identity_answers: Iterator[Any] = iter([([existing], "gtin"), ([], None)])

    async def _identity(session: Any, **_kwargs: Any) -> Any:
        del session
        return next(identity_answers)

    async def _by_sku(
        session: Any, *, supplier_name: str, supplier_sku: str
    ) -> list[Any]:
        del session, supplier_name
        return [manual] if supplier_sku == "M-1" else []

    monkeypatch.setattr(
        supplier_product_mapping_crud,
        "get_by_supplier_sku",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(crud_product, "list_by_supplier_sku", _by_sku)
    monkeypatch.setattr(crud_product, "find_by_identity", _identity)
    create = AsyncMock()
    monkeypatch.setattr(crud_product, "create_draft", create)
    session = AsyncMock()

    counts, rows = await SupplierSyncOrchestrator(_adapter()).preview_items(
        session,
        [
            _item(supplier_sku="M-1"),
            _item(supplier_sku="NEW", ean="3663970012345"),
            _item(supplier_sku="FRESH"),
            _item(supplier_sku="", name="sans ref"),
        ],
    )

    assert counts["adopted"] == 1
    assert counts["updated"] == 1
    assert counts["new"] == 1
    assert counts["skipped"] == 1
    assert counts["matched_by_gtin"] == 1
    assert [r["action"] for r in rows] == ["adopted", "updated", "new", "skipped"]
    assert rows[1]["product_name"] == "Déjà là"
    create.assert_not_awaited()
    session.commit.assert_not_awaited()
