"""« Rattacher maintenant » / « Détacher » a manual product (R4 / S8)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import (
    SupplierAttachRequest,
    admin_attach_supplier,
    admin_detach_supplier,
)
from app.core.errors import AppError
from app.features.integrations.models.supplier import Supplier, SupplierKind
from app.features.integrations.models.supplier_sync import SupplierProductMapping
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.services import suppliers as registry
from app.services.suppliers.base import (
    NormalizedPricing,
    NormalizedProductData,
    SupplierAdapter,
    SupplierHealth,
)

ADMIN = cast(User, SimpleNamespace(id=uuid.uuid4(), is_superuser=True))


class DemoAdapter(SupplierAdapter):
    adapter_key = "demo_attach"
    display_name = "Démo"
    catalog: dict[str, NormalizedPricing] = {}

    async def fetch_catalog(
        self, category: str, **filters: Any
    ) -> AsyncIterator[list[NormalizedProductData]]:
        del category, filters
        if False:
            yield []

    async def fetch_price_and_availability(
        self, skus: list[str]
    ) -> dict[str, NormalizedPricing]:
        return {sku: self.catalog[sku] for sku in skus if sku in self.catalog}

    async def health_check(self) -> SupplierHealth:
        return SupplierHealth(healthy=True, configured=True, message="ok")


@pytest.fixture(autouse=True)
def demo_adapter(monkeypatch: pytest.MonkeyPatch) -> type[DemoAdapter]:
    monkeypatch.setitem(registry.ADAPTERS, DemoAdapter.adapter_key, DemoAdapter)
    DemoAdapter.catalog = {
        "D-100": NormalizedPricing(
            supplier_sku="D-100",
            price=Decimal("41250"),
            currency="XPF",
            quantity=Decimal("7"),
            vendor_part_number="MPN-100",
            manufacturer="Acme",
        )
    }
    return DemoAdapter


async def _seed(session: AsyncSession) -> uuid.UUID:
    session.add(
        Supplier(
            code="demo",
            name="Démo",
            kind=SupplierKind.API,
            adapter_key=DemoAdapter.adapter_key,
        )
    )
    session.add(Supplier(code="fichier", name="Fichier", kind=SupplierKind.FILE))
    product = Product(
        name="Portable maison",
        description="Texte saisi à la main",
        base_price=Decimal("150000"),
    )
    session.add(product)
    product_id = product.id
    await session.commit()
    return product_id


@pytest.mark.asyncio
async def test_attach_now_adopts_with_cost_and_stock(db_session: AsyncSession) -> None:
    product_id = await _seed(db_session)

    response = await admin_attach_supplier(
        db_session,
        ADMIN,
        product_id,
        SupplierAttachRequest(supplier_name="demo", supplier_sku="D-100"),
    )

    assert response.status == "adopted"
    product = response.product
    assert product.is_supplier_managed is True
    assert product.supplier_name == "demo"
    assert product.supplier_quantity == Decimal("7.00")
    assert product.cost_amount == Decimal("41250.00")
    assert product.cost_currency == "XPF"
    assert product.name == "Portable maison"
    row = await db_session.get(Product, product_id)
    assert row is not None
    assert "name" in (row.overridden_fields or [])
    assert row.published_without_enrichment is True
    mapping = (
        await db_session.exec(
            select(SupplierProductMapping).where(
                SupplierProductMapping.local_product_id == product_id
            )
        )
    ).one()
    assert mapping.supplier_sku == "D-100"


@pytest.mark.asyncio
async def test_unknown_reference_is_refused(db_session: AsyncSession) -> None:
    product_id = await _seed(db_session)
    with pytest.raises(AppError) as refused:
        await admin_attach_supplier(
            db_session,
            ADMIN,
            product_id,
            SupplierAttachRequest(supplier_name="demo", supplier_sku="NOPE"),
        )
    assert refused.value.code == "supplier.attach.unknown_sku"
    await db_session.rollback()
    row = await db_session.get(Product, product_id)
    assert row is not None and row.is_supplier_managed is False


@pytest.mark.asyncio
async def test_reference_held_by_another_product_is_a_conflict(
    db_session: AsyncSession,
) -> None:
    product_id = await _seed(db_session)
    db_session.add(Product(name="Déjà là", supplier_name="demo", supplier_sku="D-100"))
    await db_session.commit()
    with pytest.raises(AppError) as refused:
        await admin_attach_supplier(
            db_session,
            ADMIN,
            product_id,
            SupplierAttachRequest(supplier_name="demo", supplier_sku="D-100"),
        )
    assert refused.value.status_code == 409


@pytest.mark.asyncio
async def test_file_supplier_link_waits_for_the_next_import(
    db_session: AsyncSession,
) -> None:
    product_id = await _seed(db_session)
    response = await admin_attach_supplier(
        db_session,
        ADMIN,
        product_id,
        SupplierAttachRequest(supplier_name="fichier", supplier_sku="F-1"),
    )
    assert response.status == "pending"
    assert response.product.supplier_name == "fichier"
    assert response.product.supplier_sku == "F-1"
    assert response.product.is_supplier_managed is False


@pytest.mark.asyncio
async def test_detach_makes_it_manual_again(db_session: AsyncSession) -> None:
    product_id = await _seed(db_session)
    await admin_attach_supplier(
        db_session,
        ADMIN,
        product_id,
        SupplierAttachRequest(supplier_name="demo", supplier_sku="D-100"),
    )

    detached = await admin_detach_supplier(db_session, ADMIN, product_id)

    assert detached.is_supplier_managed is False
    assert detached.supplier_name is None
    assert detached.supplier_quantity == Decimal("0.00")
    assert detached.name == "Portable maison"
    mappings = (
        await db_session.exec(
            select(SupplierProductMapping).where(
                SupplierProductMapping.local_product_id == product_id
            )
        )
    ).all()
    assert mappings == []

    with pytest.raises(AppError) as refused:
        await admin_detach_supplier(db_session, ADMIN, product_id)
    assert refused.value.code == "supplier.detach.not_linked"
