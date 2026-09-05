"""Integration: suppliers declared in the database, file import, product defaults.

Real Postgres session (see conftest). Covers:

- ``/admin/suppliers`` create / update / deactivate and their validations;
- a file supplier's catalog import creating supplier-managed products with
  cost, stock, origin and the domestic pricing mode;
- ``POST /admin/products`` filling origin and pricing mode from the supplier;
- the storefront publication conditions per pricing mode (real SQL).
"""

from __future__ import annotations

import io
import json
import uuid
from decimal import Decimal

import pytest
from fastapi import UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import admin_create_product
from app.api.routes.admin_suppliers import (
    create_supplier,
    deactivate_supplier,
    update_supplier,
)
from app.api.routes.suppliers import import_catalog_file, inspect_catalog_file
from app.core.errors import AppError
from app.features.integrations.models.supplier import (
    Supplier,
    SupplierCreate,
    SupplierKind,
    SupplierUpdate,
)
from app.features.integrations.models.supplier_sync import (
    SupplierProductMapping,
    SupplierSyncLog,
)
from app.features.place.models import Place
from app.features.product.models.product import PricingMode, Product, ProductCreate
from app.features.product.services.publication import publication_conditions
from app.features.user.models.user import User


async def _seed_admin(session: AsyncSession) -> User:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return admin


async def _fresh(session: AsyncSession, admin: User) -> User:
    """Reload the admin: every route commit expires the session's instances.

    The routes themselves read ``current_user.id`` before committing; a test
    reusing one ``User`` across several calls has to refresh it in between.
    """
    await session.refresh(admin)
    return admin


async def _seed_place(session: AsyncSession, *, code: str, country: str) -> Place:
    place = Place(name=f"Entrepôt {code}", type="warehouse", code=code, country=country)
    session.add(place)
    await session.flush()
    return place


def _upload(content: bytes, filename: str = "catalogue.csv") -> UploadFile:
    return UploadFile(file=io.BytesIO(content), filename=filename)


# ---------------------------------------------------------------------------
# /admin/suppliers
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_declares_a_domestic_file_supplier(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    place = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    place_id = place.id
    await db_session.commit()

    created = await create_supplier(
        payload=SupplierCreate(
            code="Distrib_Tahiti",
            name="Distributeur Tahiti",
            kind=SupplierKind.FILE,
            origin_place_id=place_id,
            is_domestic=True,
            price_currency="xpf",
            column_mapping={"supplier_sku": "Ref", "name": "Nom"},
        ),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )

    assert created.code == "distrib_tahiti"
    assert created.kind == SupplierKind.FILE
    assert created.is_domestic is True
    assert created.price_currency == "XPF"
    assert created.origin_place_id == place_id
    assert created.configured is True


@pytest.mark.asyncio
async def test_supplier_code_is_normalized_and_unique(db_session: AsyncSession) -> None:
    admin = await _seed_admin(db_session)
    await db_session.commit()

    with pytest.raises(ValueError):
        SupplierCreate(code="Bad Code!", name="x")

    first = await create_supplier(
        payload=SupplierCreate(code="Generic_FR", name="Générique France"),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )
    assert first.code == "generic_fr"
    assert first.kind == SupplierKind.MANUAL

    with pytest.raises(AppError) as exc_info:
        await create_supplier(
            payload=SupplierCreate(code="generic_fr", name="Doublon"),
            session=db_session,
            current_user=await _fresh(db_session, admin),
        )
    assert exc_info.value.code == "supplier.code.conflict"


@pytest.mark.asyncio
async def test_api_supplier_needs_a_registered_adapter(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    await db_session.commit()

    with pytest.raises(AppError) as exc_info:
        await create_supplier(
            payload=SupplierCreate(
                code="techdata",
                name="TechData",
                kind=SupplierKind.API,
                adapter_key="techdata",
            ),
            session=db_session,
            current_user=await _fresh(db_session, admin),
        )
    assert exc_info.value.code == "supplier.adapter.unknown"

    with pytest.raises(AppError) as exc_info:
        await create_supplier(
            payload=SupplierCreate(
                code="ingram_eu",
                name="Ingram EU",
                kind=SupplierKind.API,
                adapter_key="ingram_micro",
                settings={"environment": "sandbox", "bogus": 1},
            ),
            session=db_session,
            current_user=await _fresh(db_session, admin),
        )
    assert exc_info.value.code == "supplier.settings.unknown_keys"

    created = await create_supplier(
        payload=SupplierCreate(
            code="ingram_eu",
            name="Ingram EU",
            kind=SupplierKind.API,
            adapter_key="ingram_micro",
            sync_interval_hours=12,
            settings={"environment": "sandbox", "country_code": "DE"},
        ),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )
    assert created.adapter_key == "ingram_micro"


@pytest.mark.asyncio
async def test_update_and_deactivate_keep_the_code(db_session: AsyncSession) -> None:
    admin = await _seed_admin(db_session)
    await db_session.commit()
    await create_supplier(
        payload=SupplierCreate(code="generic_fr", name="Générique France"),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )

    updated = await update_supplier(
        code="generic_fr",
        payload=SupplierUpdate(name="Générique Europe", is_domestic=False),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )
    assert updated.name == "Générique Europe"
    assert updated.code == "generic_fr"

    deactivated = await deactivate_supplier(
        code="generic_fr",
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )
    assert deactivated.is_active is False
    assert deactivated.sync_enabled is False
    row = (
        await db_session.exec(select(Supplier).where(Supplier.code == "generic_fr"))
    ).first()
    assert row is not None and row.is_active is False


# ---------------------------------------------------------------------------
# file import
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_file_import_creates_domestic_products_with_cost_and_stock(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    origin_id = origin.id
    await db_session.commit()
    supplier = await create_supplier(
        payload=SupplierCreate(
            code="distrib_tahiti",
            name="Distributeur Tahiti",
            kind=SupplierKind.FILE,
            origin_place_id=origin_id,
            is_domestic=True,
            price_currency="XPF",
            column_mapping={
                "supplier_sku": "Ref",
                "name": "Désignation",
                "price": "Prix HT",
                "quantity": "Stock",
                "manufacturer": "Marque",
                "weight": "Poids",
            },
        ),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )
    row = (
        await db_session.exec(select(Supplier).where(Supplier.code == supplier.code))
    ).first()
    assert row is not None

    content = (
        "Ref;Désignation;Prix HT;Stock;Marque;Poids\n"
        "LOC-1;Clavier sans fil;4 500;12;Logi;0,4\n"
        "LOC-2;Souris;;3;Logi;\n"
        ";Sans référence;10;1;;\n"
    ).encode()

    inspected = await inspect_catalog_file(
        supplier=row,
        _current_user=await _fresh(db_session, admin),
        file=_upload(content),
    )
    assert inspected.headers[:2] == ["Ref", "Désignation"]
    assert inspected.mapping_problems == []

    response = await import_catalog_file(
        supplier=row,
        session=db_session,
        current_user=await _fresh(db_session, admin),
        file=_upload(content),
        mapping=None,
        dry_run=False,
    )

    assert response.parsed_products == 2
    assert response.rejected_rows == 1
    assert response.statistics["new_products"] == 2
    assert response.statistics["errors"] == 0
    assert response.sync_log_id is not None

    products = {
        p.supplier_sku: p
        for p in (
            await db_session.exec(
                select(Product).where(Product.supplier_name == "distrib_tahiti")
            )
        ).all()
    }
    keyboard = products["LOC-1"]
    assert keyboard.is_supplier_managed is True
    assert keyboard.pricing_mode == PricingMode.DOMESTIC
    assert keyboard.supplier_place_id == origin_id
    assert keyboard.cost_amount == Decimal("4500.00")
    assert keyboard.cost_currency == "XPF"
    assert keyboard.supplier_quantity == Decimal("12.00")
    assert keyboard.weight == 0.4
    mouse = products["LOC-2"]
    assert mouse.cost_amount == Decimal("0.00")  # no price column value → untouched
    assert mouse.supplier_quantity == Decimal("3.00")

    mappings = (
        await db_session.exec(
            select(SupplierProductMapping).where(
                SupplierProductMapping.supplier_name == "distrib_tahiti"
            )
        )
    ).all()
    assert {m.supplier_sku for m in mappings} == {"LOC-1", "LOC-2"}
    log = (
        await db_session.exec(
            select(SupplierSyncLog).where(
                SupplierSyncLog.supplier_name == "distrib_tahiti"
            )
        )
    ).first()
    assert log is not None and log.statistics is not None
    assert log.statistics["source"] == "file"

    # A second import of the same file updates instead of duplicating, and a
    # mapping passed inline overrides the stored one. (The first import's
    # commits expired the row: reload it as a new request would.)
    await db_session.refresh(row)
    again = await import_catalog_file(
        supplier=row,
        session=db_session,
        current_user=await _fresh(db_session, admin),
        file=_upload(content),
        mapping=json.dumps(
            {"supplier_sku": "Ref", "name": "Désignation", "quantity": "Stock"}
        ),
        dry_run=False,
    )
    assert again.statistics["new_products"] == 0
    assert again.statistics["updated_products"] == 2
    count = len(
        (
            await db_session.exec(
                select(Product).where(Product.supplier_name == "distrib_tahiti")
            )
        ).all()
    )
    assert count == 2


# ---------------------------------------------------------------------------
# manual products linked to a supplier
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_manual_product_inherits_origin_and_mode_from_its_supplier(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    origin_id = origin.id
    await db_session.commit()
    await create_supplier(
        payload=SupplierCreate(
            code="distrib_tahiti",
            name="Distributeur Tahiti",
            origin_place_id=origin_id,
            is_domestic=True,
        ),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )

    product = await admin_create_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        payload=ProductCreate(
            name="Onduleur",
            supplier_name="distrib_tahiti",
            supplier_sku="OND-1",
            cost_amount=Decimal("25000"),
            cost_currency="XPF",
            supplier_quantity=Decimal("4"),
        ),
    )

    assert product.is_supplier_managed is False
    assert product.supplier_place_id == origin_id
    assert product.pricing_mode == PricingMode.DOMESTIC
    assert product.supplier_quantity == Decimal("4.00")

    fixed = await admin_create_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        payload=ProductCreate(
            name="Câble HDMI (stock entrepôt)",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("2990"),
        ),
    )
    assert fixed.pricing_mode == PricingMode.FIXED
    assert fixed.supplier_place_id is None

    with pytest.raises(AppError) as exc_info:
        await admin_create_product(
            session=db_session,
            current_user=await _fresh(db_session, admin),
            payload=ProductCreate(name="Orphelin", supplier_name="ghost"),
        )
    assert exc_info.value.code == "supplier.not_found"


# ---------------------------------------------------------------------------
# publication conditions per mode (real SQL)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publication_conditions_follow_the_pricing_mode(
    db_session: AsyncSession,
) -> None:
    rows = [
        Product(name="import sans douane ni poids", pricing_mode=PricingMode.IMPORT),
        Product(
            name="import complet",
            pricing_mode=PricingMode.IMPORT,
            customs_rate_pct=Decimal("5"),
            weight=1.0,
        ),
        Product(name="local sans rien", pricing_mode=PricingMode.DOMESTIC),
        Product(name="fixe à zéro", pricing_mode=PricingMode.FIXED),
        Product(
            name="fixe prix",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("1500"),
        ),
    ]
    db_session.add_all(rows)
    await db_session.commit()

    published = (
        await db_session.exec(select(Product.name).where(*publication_conditions()))
    ).all()

    assert sorted(published) == ["fixe prix", "import complet", "local sans rien"]
