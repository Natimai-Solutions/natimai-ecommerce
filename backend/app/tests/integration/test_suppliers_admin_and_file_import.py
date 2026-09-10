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
from typing import Any

import pytest
from fastapi import UploadFile
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import (
    ProductPublishRequest,
    admin_create_product,
    admin_publish_products,
)
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
        publish_new=True,
    )

    assert response.parsed_products == 2
    assert response.published_new is True
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
    # Published as the file describes it: visible before (and without) Icecat.
    assert keyboard.published_without_enrichment is True
    assert keyboard.is_enriched is False
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
        publish_new=True,
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


# ---------------------------------------------------------------------------
# recognising existing products across imports
# ---------------------------------------------------------------------------


async def _seed_file_supplier(
    db_session: AsyncSession, admin: User, *, code: str, origin_id: uuid.UUID
) -> Supplier:
    await create_supplier(
        payload=SupplierCreate(
            code=code,
            name=code,
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
                "vendor_part_number": "Réf fabricant",
                "ean": "EAN",
            },
        ),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )
    row = (await db_session.exec(select(Supplier).where(Supplier.code == code))).first()
    assert row is not None
    return row


async def _run_import(
    db_session: AsyncSession,
    admin: User,
    row: Supplier,
    content: bytes,
    *,
    dry_run: bool,
    publish_new: bool = True,
) -> Any:
    await db_session.refresh(row)
    return await import_catalog_file(
        supplier=row,
        session=db_session,
        current_user=await _fresh(db_session, admin),
        file=_upload(content),
        mapping=None,
        dry_run=dry_run,
        publish_new=publish_new,
    )


async def _products_of(db_session: AsyncSession, code: str) -> list[Product]:
    return list(
        (
            await db_session.exec(select(Product).where(Product.supplier_name == code))
        ).all()
    )


@pytest.mark.asyncio
async def test_reimport_with_a_new_reference_is_recognised_by_barcode(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    origin_id = origin.id
    await db_session.commit()
    row = await _seed_file_supplier(
        db_session, admin, code="distrib_a", origin_id=origin_id
    )

    header = "Ref;Désignation;Prix HT;Stock;Marque;Réf fabricant;EAN\n"
    first = (header + "A-001;Clavier;4500;10;Logi;K120;5099206020276\n").encode()
    # Same barcode, reference renumbered, and Excel dropped the leading zero.
    second = (
        header + "K120-NEW;Clavier sans fil;4200;7;Logi;K120;5099206020276\n"
    ).encode()

    await _run_import(db_session, admin, row, first, dry_run=False)

    preview = await _run_import(db_session, admin, row, second, dry_run=True)
    assert preview.resolution["updated"] == 1
    assert preview.resolution["matched_by_gtin"] == 1
    assert preview.sample_resolutions[0].action == "updated"
    assert preview.sample_resolutions[0].match_key == "gtin"
    assert preview.sample_resolutions[0].product_name == "Clavier"

    result = await _run_import(db_session, admin, row, second, dry_run=False)
    assert result.statistics["updated_products"] == 1
    assert result.statistics["new_products"] == 0
    assert result.statistics["matched_by_gtin"] == 1

    products = await _products_of(db_session, "distrib_a")
    assert len(products) == 1
    assert products[0].supplier_sku == "K120-NEW"
    assert products[0].name == "Clavier sans fil"
    assert products[0].supplier_quantity == Decimal("7.00")

    mappings = (
        await db_session.exec(
            select(SupplierProductMapping).where(
                SupplierProductMapping.supplier_name == "distrib_a"
            )
        )
    ).all()
    assert [m.supplier_sku for m in mappings] == ["K120-NEW"]


@pytest.mark.asyncio
async def test_reimport_recognises_by_manufacturer_part_when_no_barcode(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    origin_id = origin.id
    await db_session.commit()
    row = await _seed_file_supplier(
        db_session, admin, code="distrib_a", origin_id=origin_id
    )

    header = "Ref;Désignation;Prix HT;Stock;Marque;Réf fabricant;EAN\n"
    first = (header + "A-002;Souris;1500;3;Logi;M185;\n").encode()
    second = (header + "M185-2026;Souris;1400;9; logi ;m185;\n").encode()

    await _run_import(db_session, admin, row, first, dry_run=False)
    result = await _run_import(db_session, admin, row, second, dry_run=False)

    assert result.statistics["matched_by_manufacturer_part"] == 1
    assert len(await _products_of(db_session, "distrib_a")) == 1


@pytest.mark.asyncio
async def test_manual_product_of_the_supplier_is_adopted_and_keeps_its_content(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    origin_id = origin.id
    await db_session.commit()
    row = await _seed_file_supplier(
        db_session, admin, code="distrib_a", origin_id=origin_id
    )

    manual = await admin_create_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        payload=ProductCreate(
            name="Onduleur 800 VA (fiche rédigée)",
            supplier_name="distrib_a",
            supplier_sku="OND-800",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("29900"),
        ),
    )
    manual_id = manual.id

    header = "Ref;Désignation;Prix HT;Stock;Marque;Réf fabricant;EAN\n"
    content = (header + "OND-800;ONDULEUR 800VA;18000;5;Eaton;3S800F;\n").encode()

    preview = await _run_import(db_session, admin, row, content, dry_run=True)
    assert preview.resolution["adopted"] == 1
    assert preview.sample_resolutions[0].product_id == str(manual_id)

    result = await _run_import(db_session, admin, row, content, dry_run=False)
    assert result.statistics["adopted_products"] == 1
    assert result.statistics["new_products"] == 0

    products = await _products_of(db_session, "distrib_a")
    assert len(products) == 1
    adopted = products[0]
    assert adopted.id == manual_id
    assert adopted.is_supplier_managed is True
    # Adoption makes it supplier-managed: without this it would vanish from
    # the storefront until Icecat knows it.
    assert adopted.published_without_enrichment is True
    assert adopted.name == "Onduleur 800 VA (fiche rédigée)"
    assert adopted.pricing_mode == PricingMode.FIXED
    assert adopted.base_price == Decimal("29900.00")
    assert adopted.cost_amount == Decimal("18000.00")
    assert adopted.supplier_quantity == Decimal("5.00")
    assert adopted.manufacturer == "Eaton"
    assert "name" in (adopted.overridden_fields or [])
    assert "pricing_mode" in (adopted.overridden_fields or [])


@pytest.mark.asyncio
async def test_another_supplier_product_is_never_matched(
    db_session: AsyncSession,
) -> None:
    """Same barcode at two suppliers = two products (the customer picks)."""
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    origin_id = origin.id
    await db_session.commit()
    row_a = await _seed_file_supplier(
        db_session, admin, code="distrib_a", origin_id=origin_id
    )
    row_b = await _seed_file_supplier(
        db_session, admin, code="distrib_b", origin_id=origin_id
    )

    header = "Ref;Désignation;Prix HT;Stock;Marque;Réf fabricant;EAN\n"
    content_a = (header + "A-1;Clavier;4500;10;Logi;K120;5099206020276\n").encode()
    content_b = (header + "B-9;Clavier;4100;2;Logi;K120;5099206020276\n").encode()

    await _run_import(db_session, admin, row_a, content_a, dry_run=False)
    result = await _run_import(db_session, admin, row_b, content_b, dry_run=False)

    assert result.statistics["new_products"] == 1
    assert len(await _products_of(db_session, "distrib_a")) == 1
    assert len(await _products_of(db_session, "distrib_b")) == 1


@pytest.mark.asyncio
async def test_ambiguous_identity_is_reported_and_leaves_both_untouched(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    origin_id = origin.id
    await db_session.commit()
    row = await _seed_file_supplier(
        db_session, admin, code="distrib_a", origin_id=origin_id
    )

    header = "Ref;Désignation;Prix HT;Stock;Marque;Réf fabricant;EAN\n"
    # Two products of this supplier carry the same barcode: one imported, one
    # typed by hand (the import alone would have merged a second line).
    first = (header + "A-1;Clavier noir;4500;10;Logi;K120;5099206020276\n").encode()
    await _run_import(db_session, admin, row, first, dry_run=False)
    await admin_create_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        payload=ProductCreate(
            name="Clavier blanc",
            supplier_name="distrib_a",
            supplier_sku="A-2",
            ean="5099206020276",
        ),
    )

    renumbered = (header + "A-3;Clavier;4000;1;Logi;K120;5099206020276\n").encode()
    preview = await _run_import(db_session, admin, row, renumbered, dry_run=True)
    assert preview.resolution["ambiguous"] == 1
    assert preview.sample_resolutions[0].action == "ambiguous"

    result = await _run_import(db_session, admin, row, renumbered, dry_run=False)
    assert result.statistics["ambiguous_products"] == 1
    assert result.statistics["new_products"] == 0
    assert result.sync_errors and result.sync_errors[0]["sku"] == "A-3"
    assert {p.supplier_sku for p in await _products_of(db_session, "distrib_a")} == {
        "A-1",
        "A-2",
    }


@pytest.mark.asyncio
async def test_import_can_leave_new_rows_hidden_until_enrichment(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code="PPT_DISTRIB", country="PF")
    origin_id = origin.id
    await db_session.commit()
    row = await _seed_file_supplier(
        db_session, admin, code="distrib_h", origin_id=origin_id
    )
    header = "Ref;Désignation;Prix HT;Stock;Marque;Réf fabricant;EAN\n"
    content = (header + "H-1;Câble HDMI 2 m;1200;30;NoName;;\n").encode()

    result = await _run_import(
        db_session, admin, row, content, dry_run=False, publish_new=False
    )
    assert result.published_new is False
    (product,) = await _products_of(db_session, "distrib_h")
    assert product.published_without_enrichment is False

    # The admin publishes it as it stands from the products page.
    outcome = await admin_publish_products(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        payload=ProductPublishRequest(product_ids=[product.id, uuid.uuid4()]),
    )
    assert outcome.updated == 1
    assert len(outcome.missing) == 1
    await db_session.refresh(product)
    assert product.published_without_enrichment is True
