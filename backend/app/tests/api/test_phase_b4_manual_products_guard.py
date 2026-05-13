import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.integrations.crud.supplier_sync import supplier_product_mapping_crud
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
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
    updated_mapping = SimpleNamespace(id=uuid.uuid4())

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
    update_product_mock = AsyncMock()
    create_product_mock = AsyncMock(return_value=created_product)
    upsert_mapping_mock = AsyncMock(return_value=updated_mapping)

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
    monkeypatch.setattr(crud_product, "update", update_product_mock)
    monkeypatch.setattr(crud_product, "create", create_product_mock)
    monkeypatch.setattr(
        supplier_product_mapping_crud,
        "upsert_mapping_for_sku",
        upsert_mapping_mock,
    )

    result = await orchestrator.upsert_product(session=session, item=item)

    update_product_mock.assert_not_awaited()
    create_product_mock.assert_awaited_once()
    upsert_mapping_mock.assert_awaited_once()
    assert result["action"] == "created"
    assert result["product_id"] == str(created_product.id)
