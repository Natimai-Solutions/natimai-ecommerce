import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.integrations.crud.supplier_sync import supplier_product_mapping_crud
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.place.crud import crud_place
from app.features.product.crud.product import crud_product
from app.services.suppliers import NormalizedProductData
from app.services.suppliers.ingram_micro import IngramMicroAdapter

SUPPLIER_NAME = IngramMicroAdapter.name


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_upsert_product_does_not_overwrite_manual_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = SupplierSyncOrchestrator(IngramMicroAdapter())
    session = AsyncMock()

    mapping = SimpleNamespace(id=uuid.uuid4(), local_product_id=uuid.uuid4())
    manual_product = SimpleNamespace(
        id=uuid.uuid4(),
        is_supplier_managed=False,
        supplier_name=SUPPLIER_NAME,
        supplier_sku="SKU-001",
    )
    created_product = SimpleNamespace(id=uuid.uuid4())

    item = NormalizedProductData(
        supplier_sku="SKU-001",
        name="Produit Fournisseur",
        manufacturer="Vendor",
        vendor_part_number="PART-001",
        category="Informatique",
        price=0.0,
        quantity=0,
    )

    get_mapping_mock = AsyncMock(return_value=mapping)
    get_supplier_product_mock = AsyncMock(return_value=None)
    update_draft_mock = AsyncMock()
    create_draft_mock = AsyncMock(return_value=created_product)

    session.get = AsyncMock(return_value=manual_product)

    monkeypatch.setattr(
        supplier_product_mapping_crud,
        "get_by_supplier_sku",
        get_mapping_mock,
    )
    monkeypatch.setattr(
        crud_product,
        "get_by_supplier_sku",
        get_supplier_product_mock,
    )
    monkeypatch.setattr(crud_product, "update_draft", update_draft_mock)
    monkeypatch.setattr(crud_product, "create_draft", create_draft_mock)
    # Origin-place resolution is orthogonal to the manual-product guard.
    monkeypatch.setattr(crud_place, "get_by_code", AsyncMock(return_value=None))

    result = await orchestrator.upsert_product(session=session, item=item)

    # A manual product (is_supplier_managed=False) is resolved by
    # _resolve_existing_product as "no managed product" → the orchestrator
    # creates a new supplier-managed product instead of overwriting the
    # manual one. update_draft must never run on the manual record.
    update_draft_mock.assert_not_awaited()
    create_draft_mock.assert_awaited_once()
    assert result["action"] == "created"
    assert result["product_id"] == str(created_product.id)
