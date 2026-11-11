"""What the sync does with a product typed by hand.

A manual product linked to the *same* supplier (same ``supplier_name``) is
recognised and adopted: the sync takes over its sourcing (reference, cost,
stock) and locks what the admin wrote. A manual product of another supplier,
or with no supplier, is never touched — a new supplier-managed product is
created next to it.
"""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from app.features.integrations.crud.supplier_sync import supplier_product_mapping_crud
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.place.crud import crud_place
from app.features.product.crud.category import crud_category
from app.features.product.crud.product import crud_product
from app.features.product.models.product import PricingMode
from app.services.suppliers import NormalizedProductData
from app.services.suppliers.ingram_micro import IngramMicroAdapter

SUPPLIER_NAME = IngramMicroAdapter.adapter_key


@pytest.fixture(autouse=True)
def _no_open_reservations(monkeypatch: pytest.MonkeyPatch) -> None:
    """The session here is a stand-in: no order holds supplier units, the
    supplier's count is kept as is (B4 is covered in
    integration/test_supplier_reservations.py)."""

    async def _same(_session: object, _product_id: object, count: Decimal) -> Decimal:
        return Decimal(count)

    monkeypatch.setattr(
        "app.features.integrations.services.supplier_sync_orchestrator.net_supplier_quantity",
        _same,
    )


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def _item() -> NormalizedProductData:
    return NormalizedProductData(
        supplier_sku="SKU-001",
        name="Produit Fournisseur",
        manufacturer="Vendor",
        vendor_part_number="PART-001",
        category="Informatique",
        price=12.5,
        quantity=4,
    )


def _wire(
    monkeypatch: pytest.MonkeyPatch,
    *,
    mapping: Any,
    by_sku: list[Any],
    by_identity: tuple[list[Any], str | None] = ([], None),
) -> dict[str, AsyncMock]:
    mocks = {
        "update": AsyncMock(),
        "create": AsyncMock(return_value=SimpleNamespace(id=uuid.uuid4())),
    }
    monkeypatch.setattr(
        supplier_product_mapping_crud,
        "get_by_supplier_sku",
        AsyncMock(return_value=mapping),
    )
    monkeypatch.setattr(
        supplier_product_mapping_crud, "get_by_product", AsyncMock(return_value=None)
    )
    monkeypatch.setattr(
        crud_product, "list_by_supplier_sku", AsyncMock(return_value=by_sku)
    )
    # The row's category (no subcategory) names its shop category.
    monkeypatch.setattr(
        crud_category,
        "get_or_create_by_name",
        AsyncMock(return_value=(SimpleNamespace(id=uuid.uuid4(), name="Info"), True)),
    )
    monkeypatch.setattr(
        crud_product, "find_by_identity", AsyncMock(return_value=by_identity)
    )
    monkeypatch.setattr(crud_product, "update_draft", mocks["update"])
    monkeypatch.setattr(crud_product, "create_draft", mocks["create"])
    # Origin-place resolution is orthogonal to the manual-product guard.
    monkeypatch.setattr(crud_place, "get_by_code", AsyncMock(return_value=None))
    return mocks


@pytest.mark.anyio
async def test_manual_product_of_another_supplier_is_never_overwritten(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stale mapping pointing at another supplier's product is ignored."""
    orchestrator = SupplierSyncOrchestrator(IngramMicroAdapter())
    session = AsyncMock()
    foreign_manual = SimpleNamespace(
        id=uuid.uuid4(),
        is_supplier_managed=False,
        supplier_name="generic_fr",
        supplier_sku="SKU-001",
    )
    mapping = SimpleNamespace(id=uuid.uuid4(), local_product_id=foreign_manual.id)
    session.get = AsyncMock(return_value=foreign_manual)
    mocks = _wire(monkeypatch, mapping=mapping, by_sku=[])

    result = await orchestrator.upsert_product(session=session, item=_item())

    mocks["update"].assert_not_awaited()
    mocks["create"].assert_awaited_once()
    assert result["action"] == "created"
    assert result["match_key"] == ""


@pytest.mark.anyio
async def test_manual_product_of_the_same_supplier_is_adopted_with_locks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Same supplier, same reference: the hand-typed product becomes the target.

    Its content is locked (name, fixed price, mode…) so the file only brings
    the sourcing fields; the sync will drive it from now on.
    """
    orchestrator = SupplierSyncOrchestrator(IngramMicroAdapter())
    session = AsyncMock()
    manual = SimpleNamespace(
        id=uuid.uuid4(),
        is_supplier_managed=False,
        supplier_name=SUPPLIER_NAME,
        supplier_sku="SKU-001",
        supplier_place_id=uuid.uuid4(),
        overridden_fields=None,
        name="Nom saisi par l'admin",
        description="",
        long_description=None,
        image_url="https://img/x.png",
        pricing_mode=PricingMode.FIXED,
        base_price=49990,
        margin_rate_pct=None,
        customs_rate_pct=None,
        category_id=None,
        tax_rate_id=None,
        weight=None,
        dimensions_length=None,
        dimensions_width=None,
        dimensions_height=None,
    )
    mocks = _wire(monkeypatch, mapping=None, by_sku=[manual])

    result = await orchestrator.upsert_product(session=session, item=_item())

    mocks["create"].assert_not_awaited()
    mocks["update"].assert_awaited_once()
    assert result["action"] == "adopted"
    assert result["match_key"] == "supplier_sku"

    assert mocks["update"].await_args is not None
    applied = mocks["update"].await_args.kwargs["data"].model_dump(exclude_unset=True)
    # Sourcing flows in…
    assert applied["is_supplier_managed"] is True
    assert applied["supplier_sku"] == "SKU-001"
    assert str(applied["cost_amount"]) == "12.50"
    assert str(applied["supplier_quantity"]) == "4.00"
    # …content stays the admin's, and is locked for the next runs.
    for locked in ("name", "image_url", "pricing_mode", "base_price"):
        assert locked not in applied
    assert applied["overridden_fields"] == [
        "base_price",
        "image_url",
        "name",
        "pricing_mode",
        "supplier_place_id",
    ]
