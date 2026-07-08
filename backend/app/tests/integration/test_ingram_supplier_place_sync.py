"""Integration: supplier sync stamps ``supplier_place_id`` from the origin place.

The orchestrator resolves the adapter's ``origin_place_code`` to a ``Place`` id
(idempotent ``get_by_code``) and stamps it on synced products — without ever
clobbering a manual admin override on subsequent syncs.
"""

import uuid
from types import SimpleNamespace

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.services.suppliers.base import NormalizedProductData


def _orchestrator(origin_place_code: str | None) -> SupplierSyncOrchestrator:
    # Only ``name`` and ``origin_place_code`` are read on the upsert path.
    adapter = SimpleNamespace(name="ingram_micro", origin_place_code=origin_place_code)
    return SupplierSyncOrchestrator(adapter)  # type: ignore[arg-type]


def _item(sku: str) -> NormalizedProductData:
    return NormalizedProductData(
        supplier_sku=sku, name=f"Product {sku}", manufacturer="ACME"
    )


async def _seed_origin(session: AsyncSession) -> Place:
    place = Place(
        name="Entrepôt fournisseurs (France)",
        type="warehouse",
        code="FR_SUPPLIERS",
        country="FR",
        is_warehouse=True,
    )
    session.add(place)
    await session.flush()
    return place


@pytest.mark.asyncio
async def test_sync_stamps_supplier_place_id_on_create(
    db_session: AsyncSession,
) -> None:
    origin = await _seed_origin(db_session)
    origin_id = origin.id  # capture before commit (commit expires ORM instances)
    result = await _orchestrator("FR_SUPPLIERS").upsert_product(db_session, _item("A1"))
    await db_session.commit()

    product = await db_session.get(Product, uuid.UUID(result["product_id"]))
    assert product is not None
    assert product.supplier_place_id == origin_id


@pytest.mark.asyncio
async def test_sync_does_not_clobber_manual_origin(
    db_session: AsyncSession,
) -> None:
    await _seed_origin(db_session)
    other = Place(name="Autre origine", type="warehouse", code="OTHER", country="US")
    db_session.add(other)
    await db_session.flush()
    other_id = other.id  # capture before commit (commit expires ORM instances)

    # First sync creates the product with the default origin.
    result = await _orchestrator("FR_SUPPLIERS").upsert_product(db_session, _item("A2"))
    await db_session.commit()
    product_id = uuid.UUID(result["product_id"])

    # An admin manually overrides the origin.
    product = await db_session.get(Product, product_id)
    assert product is not None
    product.supplier_place_id = other_id
    db_session.add(product)
    await db_session.commit()

    # A subsequent sync must NOT overwrite the manual override.
    await _orchestrator("FR_SUPPLIERS").upsert_product(db_session, _item("A2"))
    await db_session.commit()

    refreshed = await db_session.get(Product, product_id)
    assert refreshed is not None
    assert refreshed.supplier_place_id == other_id


@pytest.mark.asyncio
async def test_sync_respects_overridden_fields(db_session: AsyncSession) -> None:
    # First sync creates the supplier product.
    result = await _orchestrator(None).upsert_product(db_session, _item("A4"))
    await db_session.commit()
    product_id = uuid.UUID(result["product_id"])

    # An admin edits the name and locks it against future syncs.
    product = await db_session.get(Product, product_id)
    assert product is not None
    product.name = "Nom choisi par l'admin"
    product.overridden_fields = ["name"]
    db_session.add(product)
    await db_session.commit()

    # A later sync tries to change the name — it must be preserved.
    incoming = NormalizedProductData(
        supplier_sku="A4", name="Nom fournisseur", manufacturer="ACME"
    )
    await _orchestrator(None).upsert_product(db_session, incoming)
    await db_session.commit()

    refreshed = await db_session.get(Product, product_id)
    assert refreshed is not None
    assert refreshed.name == "Nom choisi par l'admin"


@pytest.mark.asyncio
async def test_sync_unknown_origin_code_leaves_unset(
    db_session: AsyncSession,
) -> None:
    # No Place seeded for this code → origin cannot be resolved.
    result = await _orchestrator("DOES_NOT_EXIST").upsert_product(
        db_session, _item("A3")
    )
    await db_session.commit()

    product = await db_session.get(Product, uuid.UUID(result["product_id"]))
    assert product is not None
    assert product.supplier_place_id is None
