"""Integration (real DB): the product comparator (R8 / confort) — spec rows
across the shortlist, highlighted specs first, stale ids ignored."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.product_catalog import compare_products
from app.features.product.models.product import PricingMode, Product
from app.features.product.services.spec_projection import upsert_product_specs


def _laptop(name: str, specs: list[dict[str, str]]) -> Product:
    return Product(
        name=name,
        supplier_name="tahiti",
        supplier_sku=f"tahiti-{uuid.uuid4().hex[:6]}",
        supplier_category="Ordinateur portable",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("149900"),
        supplier_quantity=Decimal("3"),
        manufacturer="Lenovo",
        is_enriched=True,
        technical_specifications=specs,
    )


@pytest.mark.asyncio
async def test_rows_cover_the_union_of_specs(db_session: AsyncSession) -> None:
    a = _laptop(
        "E14",
        [
            {"name": "Famille de processeur", "value": "Intel Core Ultra 5"},
            {"name": "Mémoire installée", "value": "16 Go"},
            {"name": "Taille de l'écran", "value": '14"'},
        ],
    )
    b = _laptop(
        "E16",
        [
            {"name": "Mémoire installée", "value": "32 Go"},
            {"name": "Capacité du SSD", "value": "1024 Go"},
            {"name": "Taille de l'écran", "value": '16"'},
        ],
    )
    db_session.add_all([a, b])
    await db_session.flush()
    await upsert_product_specs(db_session, a)
    await upsert_product_specs(db_session, b)
    a_id, b_id = a.id, b.id
    await db_session.commit()

    result = await compare_products(
        db_session, ids=[a_id, b_id, b_id, uuid.uuid4()], current_user=None
    )
    assert [p.id for p in result.products] == [a_id, b_id]
    assert result.products[0].available_quantity == Decimal("3")
    rows = {r.key: r for r in result.rows}
    # Highlighted specs come first, in their rank order.
    assert [r.key for r in result.rows[:4]] == [
        "cpu_family",
        "memory_gb",
        "storage_gb",
        "screen_inches",
    ]
    assert rows["memory_gb"].label == "Mémoire RAM"
    assert rows["memory_gb"].values == {str(a_id): "16 Go", str(b_id): "32 Go"}
    assert rows["cpu_family"].values[str(b_id)] is None
    assert rows["storage_gb"].values == {str(a_id): None, str(b_id): "1 To"}
    assert rows["screen_inches"].values[str(a_id)] == "14\u00a0pouces"


@pytest.mark.asyncio
async def test_unknown_products_only_give_an_empty_table(
    db_session: AsyncSession,
) -> None:
    result = await compare_products(db_session, ids=[uuid.uuid4()], current_user=None)
    assert result.products == [] and result.rows == []
