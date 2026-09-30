"""Minimum quantity / price of a supplier's file import (R4 / S2).

A new row under the minimum is not created; an existing product under it is
refreshed and taken off the storefront, and comes back once above it. A row
without the value is not judged. The dry run counts all of it.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_suppliers import update_supplier
from app.api.routes.suppliers import import_catalog_file
from app.core.config import settings
from app.features.integrations.models.supplier import Supplier, SupplierUpdate
from app.features.integrations.services.supplier_sync_orchestrator import (
    ImportThresholds,
)
from app.services.suppliers.base import NormalizedProductData
from app.tests.integration.test_suppliers_admin_and_file_import import (
    _fresh,
    _products_of,
    _seed_admin,
    _seed_file_supplier,
    _seed_place,
    _upload,
)

HEADER = "Ref;Désignation;Prix HT;Stock;Marque;Réf fabricant;EAN\n"


@pytest.fixture(autouse=True)
def _no_subcategory_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    # The global allowlist (computers only) would deactivate these rows.
    monkeypatch.setattr(settings, "SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST", [])


def test_verdict_only_judges_what_the_row_carries() -> None:
    thresholds = ImportThresholds(min_quantity=Decimal("5"), min_price=Decimal("100"))
    row = NormalizedProductData(supplier_sku="A", name="A")
    assert thresholds.verdict(row) is None
    row.quantity = Decimal("4")
    assert thresholds.verdict(row) == "below"
    row.quantity = Decimal("5")
    assert thresholds.verdict(row) == "meets"
    row.price = Decimal("99.99")
    assert thresholds.verdict(row) == "below"
    assert ImportThresholds().active is False
    assert ImportThresholds(min_quantity=Decimal("0")).active is False


async def _setup(db_session: AsyncSession, code: str) -> tuple[Any, Supplier]:
    admin = await _seed_admin(db_session)
    origin = await _seed_place(db_session, code=f"P_{code}", country="PF")
    origin_id = origin.id
    await db_session.commit()
    row = await _seed_file_supplier(db_session, admin, code=code, origin_id=origin_id)
    return admin, row


async def _import(
    db_session: AsyncSession,
    admin: Any,
    row: Supplier,
    content: bytes,
    *,
    dry_run: bool = False,
    min_quantity: Decimal | None = None,
) -> Any:
    await db_session.refresh(row)
    return await import_catalog_file(
        supplier=row,
        session=db_session,
        current_user=await _fresh(db_session, admin),
        file=_upload(content),
        mapping=None,
        dry_run=dry_run,
        min_quantity=min_quantity,
    )


@pytest.mark.asyncio
async def test_supplier_minimum_applies_to_new_and_existing_rows(
    db_session: AsyncSession,
) -> None:
    admin, row = await _setup(db_session, "distrib_seuil")
    code = row.code
    first = (
        HEADER + "S-1;Écran 24;15000;8;Acme;;\n" + "S-2;Écran 27;21000;20;Acme;;\n"
    ).encode()
    await _import(db_session, admin, row, first)

    await update_supplier(
        code,
        SupplierUpdate(min_quantity=Decimal("10")),
        db_session,
        await _fresh(db_session, admin),
    )
    await db_session.refresh(row)
    assert row.min_quantity == Decimal("10")

    second = (
        HEADER
        + "S-1;Écran 24;15000;3;Acme;;\n"  # existing, now under the minimum
        + "S-2;Écran 27;21000;25;Acme;;\n"
        + "S-3;Écran 32;30000;2;Acme;;\n"  # new, under the minimum
        + "S-4;Écran 34;35000;40;Acme;;\n"
    ).encode()

    preview = await _import(db_session, admin, row, second, dry_run=True)
    assert preview.resolution["below_threshold"] == 2
    assert preview.resolution["new"] == 1
    actions = {r.supplier_sku: r.action for r in preview.sample_resolutions}
    assert actions["S-3"] == "below_threshold"
    assert actions["S-1"] == "updated"

    response = await _import(db_session, admin, row, second)
    assert response.statistics["below_threshold_skipped"] == 1
    assert response.statistics["below_threshold_deactivated"] == 1
    assert response.statistics["new_products"] == 1

    products = {p.supplier_sku: p for p in await _products_of(db_session, code)}
    assert set(products) == {"S-1", "S-2", "S-4"}
    assert products["S-1"].supplier_quantity == Decimal("3.00")
    assert products["S-1"].is_active is False
    assert products["S-2"].is_active is True

    # Back above the minimum: back on the storefront.
    third = (HEADER + "S-1;Écran 24;15000;12;Acme;;\n").encode()
    await _import(db_session, admin, row, third)
    products = {p.supplier_sku: p for p in await _products_of(db_session, code)}
    assert products["S-1"].is_active is True


@pytest.mark.asyncio
async def test_run_override_and_rows_without_quantity(
    db_session: AsyncSession,
) -> None:
    admin, row = await _setup(db_session, "distrib_override")
    code = row.code
    await update_supplier(
        code,
        SupplierUpdate(min_quantity=Decimal("10")),
        db_session,
        await _fresh(db_session, admin),
    )
    content = (
        HEADER
        + "O-1;Clavier;2000;1;Acme;;\n"
        + "O-2;Souris;1500;;Acme;;\n"  # no quantity: not judged
    ).encode()

    # 0 given for this run disables the supplier's minimum.
    response = await _import(db_session, admin, row, content, min_quantity=Decimal("0"))
    assert response.statistics["new_products"] == 2
    assert response.statistics["below_threshold_skipped"] == 0

    admin2, row2 = await _setup(db_session, "distrib_default")
    code2 = row2.code
    await update_supplier(
        code2,
        SupplierUpdate(min_quantity=Decimal("10")),
        db_session,
        await _fresh(db_session, admin2),
    )
    response = await _import(db_session, admin2, row2, content)
    assert response.statistics["below_threshold_skipped"] == 1
    assert {p.supplier_sku for p in await _products_of(db_session, code2)} == {"O-2"}
