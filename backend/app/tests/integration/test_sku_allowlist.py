"""Integration tests (real DB): the supplier SKU allowlist — what the admin
saves, what leaves the storefront, what the syncs still touch."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_suppliers import get_sku_allowlist, put_sku_allowlist
from app.features.integrations.models.supplier import Supplier, SupplierKind
from app.features.integrations.services.sku_allowlist import (
    AllowlistWrite,
    allowed_sku,
    normalize_skus,
    restrict_skus,
)
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.services.suppliers.base import NormalizedProductData, SupplierConfig


def test_list_helpers() -> None:
    assert normalize_skus([" A1 ", "", "B2", "A1", "  "]) == ["A1", "B2"]
    assert allowed_sku(None, "X") and allowed_sku([], "X")
    assert allowed_sku(["A1"], "A1") and not allowed_sku(["A1"], "B2")
    assert not allowed_sku(["A1"], None)
    assert restrict_skus([], ["A1", "B2"]) == ["A1", "B2"]
    assert restrict_skus(["B2"], ["A1", "B2", "C3"]) == ["B2"]
    config = SupplierConfig.from_row(
        SimpleNamespace(code="ingram_micro", sku_allowlist=["A1"])
    )
    assert config.sku_allowlist == ["A1"]


@pytest.mark.asyncio
async def test_the_list_decides_what_is_created_refreshed_and_shown(
    db_session: AsyncSession,
) -> None:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    code = f"ingram_{uuid.uuid4().hex[:6]}"
    supplier = Supplier(code=code, name="Ingram test", kind=SupplierKind.API)
    followed = Product(
        name="Écran suivi",
        supplier_name=code,
        supplier_sku="IM-1",
        is_supplier_managed=True,
        supplier_quantity=Decimal("3"),
    )
    dropped = Product(
        name="Câble hors liste",
        supplier_name=code,
        supplier_sku="IM-2",
        is_supplier_managed=True,
        supplier_quantity=Decimal("9"),
    )
    manual = Product(name="Article maison", supplier_name=code, supplier_sku="MAN-1")
    db_session.add_all([admin, supplier, followed, dropped, manual])
    await db_session.flush()
    admin_view = cast(User, SimpleNamespace(id=admin.id))
    followed_id, dropped_id, manual_id = followed.id, dropped.id, manual.id
    supplier_id = supplier.id
    await db_session.commit()

    # Saving the list: trimmed and deduplicated, the known/unknown split is
    # reported, and the managed product outside the list leaves the shop.
    saved = await put_sku_allowlist(
        code,
        AllowlistWrite(skus=[" IM-1 ", "IM-1", "IM-9", ""]),
        db_session,
        admin_view,
    )
    assert [e.supplier_sku for e in saved.entries] == ["IM-1", "IM-9"]
    assert saved.known == 1 and saved.unknown == ["IM-9"]
    assert saved.entries[0].product_name == "Écran suivi" and saved.entries[0].is_active
    assert saved.deactivated == 1 and saved.outside == 1
    assert (await db_session.get(Product, dropped_id)).is_active is False  # type: ignore[union-attr]
    assert (await db_session.get(Product, followed_id)).is_active is True  # type: ignore[union-attr]
    # A product typed by hand is not the sync's, so the list leaves it alone.
    assert (await db_session.get(Product, manual_id)).is_active is True  # type: ignore[union-attr]

    read = await get_sku_allowlist(code, db_session, admin_view)
    assert read.model_dump(exclude={"deactivated"}) == saved.model_dump(
        exclude={"deactivated"}
    )
    assert read.deactivated == 0

    # The catalogue sync writes nothing for a reference outside the list.
    row = await db_session.get(Supplier, supplier_id)
    assert row is not None and row.sku_allowlist == ["IM-1", "IM-9"]
    adapter = SimpleNamespace(
        name=code,
        origin_place_id=None,
        origin_place_code=None,
        is_domestic=False,
        price_currency="USD",
        default_categories=[],
        sku_allowlist=list(row.sku_allowlist),
    )
    orchestrator = SupplierSyncOrchestrator(cast(Any, adapter))
    outside = await orchestrator.upsert_product(
        db_session, NormalizedProductData(supplier_sku="IM-2", name="Câble v2")
    )
    assert outside == {"action": "filtered", "product_id": ""}
    listed = await orchestrator.upsert_product(
        db_session, NormalizedProductData(supplier_sku="IM-9", name="Nouveau suivi")
    )
    assert listed["action"] == "created"
    await db_session.rollback()

    # Clearing the list follows the whole catalogue again (nothing re-shown
    # by itself: the next price / stock refresh decides).
    cleared = await put_sku_allowlist(
        code, AllowlistWrite(skus=[]), db_session, admin_view
    )
    assert cleared.entries == [] and cleared.outside == 0
    row = await db_session.get(Supplier, supplier_id)
    assert row is not None and row.sku_allowlist is None
