"""Integration: the storefront shows the stock the checkout will accept.

Real Postgres. A warehouse-only product (no supplier) sells from its
``Inventory`` row: the search « en stock » filter, the grouping tie-break and
the serialized ``available_quantity`` all read warehouse + supplier stock,
with the supplier part counted only when the product has a supplier — the
same rule the checkout reservation applies.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.inventory.models.inventory import Inventory
from app.features.inventory.services.availability import (
    publish_with_availability,
)
from app.features.product.crud.product import crud_product
from app.features.product.models.product import PricingMode, Product
from app.tasks.pricing_tasks import refresh_sale_prices


def _product(
    name: str,
    *,
    supplier: str | None,
    supplier_qty: str,
    ean: str | None = None,
    price: str = "10000",
    enriched: bool = True,
    supplier_managed: bool = False,
) -> Product:
    return Product(
        name=name,
        description="article de test",
        supplier_name=supplier,
        supplier_sku=f"{supplier}-{name}" if supplier else None,
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal(price),
        supplier_quantity=Decimal(supplier_qty),
        ean=ean,
        is_enriched=enriched,
        is_supplier_managed=supplier_managed,
    )


async def _seed(db_session: AsyncSession) -> dict[str, Product]:
    products = {
        # Own stock only: 10 units at the warehouse, no supplier.
        "warehouse": _product("Câble HDMI (entrepôt)", supplier=None, supplier_qty="0"),
        # Column filled but no supplier: nobody to draw from → not sellable.
        "orphan": _product("Câble USB (orphelin)", supplier=None, supplier_qty="5"),
        # Manual product linked to a supplier: its supplier stock counts.
        "linked": _product(
            "Câble DP (fournisseur)", supplier="tahiti", supplier_qty="4"
        ),
        # Same item at two sources, same price: the one in stock wins the group.
        "twin_out": _product(
            "Souris (fournisseur, rupture)",
            supplier="france",
            supplier_qty="0",
            ean="0196188000009",
        ),
        "twin_local": _product(
            "Souris (entrepôt)", supplier=None, supplier_qty="0", ean="0196188000009"
        ),
    }
    db_session.add_all(products.values())
    await db_session.flush()
    db_session.add_all(
        [
            Inventory(
                product_id=products["warehouse"].id,
                place_id=None,
                quantity=Decimal("10"),
                compute_from_movements=False,
            ),
            Inventory(
                product_id=products["twin_local"].id,
                place_id=None,
                quantity=Decimal("2"),
                compute_from_movements=False,
            ),
        ]
    )
    await db_session.commit()
    await refresh_sale_prices(db_session)
    for product in products.values():
        await db_session.refresh(product)
    return products


def _names(result: dict[str, Any]) -> set[str]:
    return {p.name for p in result["data"]}


@pytest.mark.asyncio
async def test_in_stock_filter_counts_warehouse_stock(db_session: AsyncSession) -> None:
    await _seed(db_session)

    in_stock = await crud_product.search_products(
        db_session, in_stock=True, group_offers=False
    )
    assert _names(in_stock) == {
        "Câble HDMI (entrepôt)",
        "Câble DP (fournisseur)",
        "Souris (entrepôt)",
    }

    out_of_stock = await crud_product.search_products(
        db_session, in_stock=False, group_offers=False
    )
    assert _names(out_of_stock) == {
        "Câble USB (orphelin)",
        "Souris (fournisseur, rupture)",
    }


@pytest.mark.asyncio
async def test_grouping_prefers_the_offer_with_sellable_stock(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)

    grouped = await crud_product.search_products(db_session, q="Souris")
    assert _names(grouped) == {"Souris (entrepôt)"}
    assert grouped["count"] == 1


@pytest.mark.asyncio
async def test_public_products_carry_the_sellable_quantity(
    db_session: AsyncSession,
) -> None:
    products = await _seed(db_session)

    publics = {
        p.name: p
        for p in await publish_with_availability(db_session, list(products.values()))
    }

    warehouse = publics["Câble HDMI (entrepôt)"]
    assert warehouse.local_quantity == Decimal("10")
    assert warehouse.available_quantity == Decimal("10")

    orphan = publics["Câble USB (orphelin)"]
    assert orphan.local_quantity == Decimal("0")
    assert orphan.available_quantity == Decimal("0")
    assert orphan.supplier_quantity == Decimal("5")  # the raw column is untouched

    linked = publics["Câble DP (fournisseur)"]
    assert linked.available_quantity == Decimal("4")

    # The row-less case is zero, never ``None``, on a storefront serialization.
    assert all(p.available_quantity is not None for p in publics.values())


@pytest.mark.asyncio
async def test_manual_products_are_published_without_enrichment(
    db_session: AsyncSession,
) -> None:
    """The admin's own product needs no Icecat pass; a bare synced row does."""
    manual = _product(
        "Câble entrepôt (saisi)", supplier=None, supplier_qty="0", enriched=False
    )
    synced = _product(
        "Ligne fournisseur brute",
        supplier="ingram",
        supplier_qty="3",
        enriched=False,
        supplier_managed=True,
    )
    db_session.add_all([manual, synced])
    await db_session.flush()
    db_session.add(
        Inventory(
            product_id=manual.id,
            place_id=None,
            quantity=Decimal("1"),
            compute_from_movements=False,
        )
    )
    await db_session.commit()
    await refresh_sale_prices(db_session)

    everything = await crud_product.search_products(db_session, group_offers=False)
    assert _names(everything) == {"Câble entrepôt (saisi)"}

    in_stock = await crud_product.search_products(
        db_session, in_stock=True, group_offers=False
    )
    assert _names(in_stock) == {"Câble entrepôt (saisi)"}


@pytest.mark.asyncio
async def test_popular_products_rank_by_views_and_hide_the_unpublishable(
    db_session: AsyncSession,
) -> None:
    """Views count once per page load; a hidden product never ranks."""
    from app.features.product.services.popularity import (
        popular_products,
        record_product_view,
    )

    products = await _seed(db_session)
    hidden = _product(
        "Ligne brute (masquée)",
        supplier="ingram",
        supplier_qty="1",
        enriched=False,
        supplier_managed=True,
    )
    db_session.add(hidden)
    await db_session.commit()

    for _ in range(3):
        await record_product_view(db_session, product_id=products["warehouse"].id)
    await record_product_view(db_session, product_id=products["linked"].id)
    for _ in range(5):
        await record_product_view(db_session, product_id=hidden.id)

    ranked = await popular_products(
        db_session, conditions=crud_product.storefront_conditions(), days=30, limit=5
    )
    assert [p.name for p in ranked][:2] == [
        "Câble HDMI (entrepôt)",
        "Câble DP (fournisseur)",
    ]
    assert all(p.name != "Ligne brute (masquée)" for p in ranked)
