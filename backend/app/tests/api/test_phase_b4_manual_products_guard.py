import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.features.integrations.crud.ingram_sync import ingram_product_mapping_crud
from app.features.integrations.services.ingram_sync_orchestrator import (
    SUPPLIER_NAME,
    IngramSyncOrchestrator,
)
from app.features.product.crud.product import crud_product
from app.services.ingram_micro_service import IngramProductData


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_upsert_product_does_not_overwrite_manual_product(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    orchestrator = IngramSyncOrchestrator()
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

    ingram_product = IngramProductData(
        sku="SKU-001",
        vendor_part_number="PART-001",
        manufacturer="Vendor",
        product_name="Produit Fournisseur",
        category="Informatique",
        price=0.0,
        availability=0,
    )

    get_mapping_mock = AsyncMock(return_value=mapping)
    get_supplier_product_mock = AsyncMock(return_value=None)
    update_product_mock = AsyncMock()
    create_product_mock = AsyncMock(return_value=created_product)
    upsert_mapping_mock = AsyncMock(return_value=updated_mapping)

    session.get = AsyncMock(return_value=manual_product)

    monkeypatch.setattr(
        ingram_product_mapping_crud,
        "get_by_ingram_sku",
        get_mapping_mock,
    )
    monkeypatch.setattr(
        crud_product,
        "get_by_supplier_sku",
        get_supplier_product_mock,
    )
    monkeypatch.setattr(
        crud_product,
        "update",
        update_product_mock,
    )
    monkeypatch.setattr(
        crud_product,
        "create",
        create_product_mock,
    )
    monkeypatch.setattr(
        ingram_product_mapping_crud,
        "upsert_mapping_for_sku",
        upsert_mapping_mock,
    )

    result = await orchestrator.upsert_product(
        session=session,
        ingram_product=ingram_product,
    )

    update_product_mock.assert_not_awaited()
    create_product_mock.assert_awaited_once()
    upsert_mapping_mock.assert_awaited_once()
    assert result["action"] == "created"
    assert result["product_id"] == str(created_product.id)
