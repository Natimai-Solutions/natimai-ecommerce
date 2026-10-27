"""Integration: the storefront search runs entirely in SQL.

Real Postgres. Filters (price, stock, specs through ``product_specs``), one
row per physical item with ``offers_count``, exact ``count`` and pagination,
facets by aggregate, ``group_offers=false``, and the fallback that prices a
not-yet-cached row landing in the page.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.crud.product import crud_product
from app.features.product.models.category import Category
from app.features.product.models.product import PricingMode, Product, ProductCondition
from app.features.product.models.product_spec import ProductSpec
from app.tasks.pricing_tasks import refresh_sale_prices


def _product(
    name: str,
    price: str,
    *,
    manufacturer: str | None = "HP Inc.",
    qty: str = "5",
    ean: str | None = None,
    category_id: Any = None,
    supplier: str = "tahiti",
) -> Product:
    return Product(
        name=name,
        description="ordinateur portable",
        supplier_name=supplier,
        supplier_sku=f"{supplier}-{name}",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal(price),
        supplier_quantity=Decimal(qty),
        manufacturer=manufacturer,
        ean=ean,
        category_id=category_id,
        is_enriched=True,
        is_supplier_managed=True,
    )


async def _seed(db_session: AsyncSession) -> dict[str, Any]:
    laptops = Category(name="Portables", is_active=True)
    screens = Category(name="Écrans", is_active=True)
    db_session.add_all([laptops, screens])
    await db_session.flush()

    products = {
        # Same laptop at two suppliers: the cheaper one is out of stock.
        "hp_a": _product(
            "HP 250 (A)", "120000", ean="0196188000001", category_id=laptops.id
        ),
        "hp_b": _product(
            "HP 250 (B)",
            "115000",
            qty="0",
            ean="0196188000001",
            category_id=laptops.id,
            supplier="france",
        ),
        "hp_lower": _product(
            "HP 255", "80000", manufacturer="hp inc.", category_id=laptops.id
        ),
        "dell": _product(
            "Dell Vostro", "45000", manufacturer="Dell", category_id=laptops.id
        ),
        "nobrand": _product(
            "Écran 24 pouces", "30000", manufacturer=None, category_id=screens.id
        ),
        "hidden": _product("HP brouillon", "10", category_id=laptops.id),
    }
    products["hidden"].is_enriched = False
    db_session.add_all(products.values())
    await db_session.flush()
    db_session.add_all(
        [
            ProductSpec(
                product_id=products["hp_a"].id,
                spec_key="memory_gb",
                value_numeric=Decimal("16"),
            ),
            ProductSpec(
                product_id=products["hp_lower"].id,
                spec_key="memory_gb",
                value_numeric=Decimal("8"),
            ),
            ProductSpec(
                product_id=products["dell"].id,
                spec_key="memory_gb",
                value_numeric=Decimal("16"),
            ),
            ProductSpec(
                product_id=products["dell"].id, spec_key="color", value_text="black"
            ),
            ProductSpec(
                product_id=products["hp_lower"].id,
                spec_key="color",
                value_text="silver",
            ),
        ]
    )
    await db_session.commit()
    await refresh_sale_prices(db_session)
    for product in products.values():
        await db_session.refresh(product)
    return {"laptops": laptops, "screens": screens, **products}


def _names(result: dict[str, Any]) -> set[str]:
    return {p.name for p in result["data"]}


@pytest.mark.asyncio
async def test_price_and_stock_filters_use_the_cached_price(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)

    cheap = await crud_product.search_products(db_session, price_max=Decimal("50000"))
    assert _names(cheap) == {"Dell Vostro", "Écran 24 pouces"}
    assert cheap["count"] == 2

    band = await crud_product.search_products(
        db_session, price_min=Decimal("80000"), price_max=Decimal("120000")
    )
    # The HP 250 group is represented by its cheapest offer (115 000, B).
    assert _names(band) == {"HP 250 (B)", "HP 255"}

    in_stock = await crud_product.search_products(
        db_session, price_min=Decimal("100000"), in_stock=True
    )
    assert _names(in_stock) == {"HP 250 (A)"}


@pytest.mark.asyncio
async def test_spec_filters_read_the_projected_specs(db_session: AsyncSession) -> None:
    await _seed(db_session)

    sixteen = await crud_product.search_products(db_session, specs={"memory_gb": 16})
    assert _names(sixteen) == {"HP 250 (A)", "Dell Vostro"}

    at_least_twelve = await crud_product.search_products(
        db_session, specs={"memory_gb_min": "12"}
    )
    assert _names(at_least_twelve) == {"HP 250 (A)", "Dell Vostro"}

    colours = await crud_product.search_products(
        db_session, specs={"color": ["Black", "white"]}
    )
    assert _names(colours) == {"Dell Vostro"}

    combined = await crud_product.search_products(
        db_session, specs={"memory_gb": 16, "color": "black"}
    )
    assert _names(combined) == {"Dell Vostro"}


@pytest.mark.asyncio
async def test_grouping_keeps_the_cheapest_offer_and_counts(
    db_session: AsyncSession,
) -> None:
    seeded = await _seed(db_session)

    grouped = await crud_product.search_products(db_session, q="hp")
    assert grouped["count"] == 2
    assert _names(grouped) == {"HP 250 (B)", "HP 255"}
    assert grouped["offers_counts"] == {str(seeded["hp_b"].id): 2}
    hp_b = next(p for p in grouped["data"] if p.name == "HP 250 (B)")
    assert hp_b.base_price == Decimal("115000.00")

    flat = await crud_product.search_products(db_session, q="hp", group_offers=False)
    assert flat["count"] == 3
    assert _names(flat) == {"HP 250 (A)", "HP 250 (B)", "HP 255"}
    assert flat["offers_counts"] == {}


@pytest.mark.asyncio
async def test_count_and_pagination_are_exact(db_session: AsyncSession) -> None:
    await _seed(db_session)

    first = await crud_product.search_products(db_session, limit=2, offset=0)
    second = await crud_product.search_products(db_session, limit=2, offset=2)
    third = await crud_product.search_products(db_session, limit=2, offset=4)

    assert first["count"] == second["count"] == third["count"] == 4
    assert len(first["data"]) == 2 and len(second["data"]) == 2
    assert third["data"] == []
    assert _names(first) | _names(second) == {
        "HP 250 (B)",
        "HP 255",
        "Dell Vostro",
        "Écran 24 pouces",
    }


@pytest.mark.asyncio
async def test_facets_are_aggregated_on_the_grouped_result(
    db_session: AsyncSession,
) -> None:
    seeded = await _seed(db_session)

    result = await crud_product.search_products(db_session)
    facets = result["facets"]

    # "HP Inc." and "hp inc." collapse into one facet; None becomes "unknown".
    by_key = {
        label.casefold(): count for label, count in facets["manufacturers"].items()
    }
    assert by_key == {"hp inc.": 2, "dell": 1, "unknown": 1}
    assert len(facets["manufacturers"]) == 3

    assert facets["categories"] == {
        str(seeded["laptops"].id): 3,
        str(seeded["screens"].id): 1,
    }
    assert facets["price_ranges"] == {"0-49999": 2, "50000-99999": 1, "100000+": 1}

    filtered = await crud_product.search_products(db_session, manufacturer="dell")
    assert filtered["facets"]["manufacturers"] == {"Dell": 1}
    assert filtered["facets"]["price_ranges"] == {
        "0-49999": 1,
        "50000-99999": 0,
        "100000+": 0,
    }


@pytest.mark.asyncio
async def test_unpriced_rows_in_the_page_are_priced_and_persisted(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)
    late = _product("Souris sans prix calculé", "2500", manufacturer="Logi")
    db_session.add(late)
    await db_session.commit()
    await db_session.refresh(late)
    assert late.sale_price_cached is None

    result = await crud_product.search_products(db_session, q="souris")
    assert [p.name for p in result["data"]] == ["Souris sans prix calculé"]
    assert result["data"][0].base_price == Decimal("2500.00")

    await db_session.refresh(late)
    assert late.sale_price_cached == Decimal("2500.00")
    assert late.sale_price_cached_at is not None


@pytest.mark.asyncio
async def test_condition_filter_separates_new_from_refurbished(
    db_session: AsyncSession,
) -> None:
    await _seed(db_session)
    refurb = _product("HP 250 (refurb)", "60000", qty="3")
    refurb.condition = ProductCondition.REFURBISHED
    refurb.condition_grade = "A"
    db_session.add(refurb)
    await db_session.commit()
    await refresh_sale_prices(db_session)

    everything = await crud_product.search_products(db_session)
    assert "HP 250 (refurb)" in _names(everything)

    refurbished = await crud_product.search_products(
        db_session, condition=ProductCondition.REFURBISHED.value
    )
    assert _names(refurbished) == {"HP 250 (refurb)"}

    new_only = await crud_product.search_products(
        db_session, condition=ProductCondition.NEW.value
    )
    assert "HP 250 (refurb)" not in _names(new_only)
    assert new_only["count"] == everything["count"] - 1


def test_prefix_tsquery_matches_every_word_as_a_prefix() -> None:
    from app.features.product.crud.product import prefix_tsquery

    assert prefix_tsquery("242") == "'242':*"
    assert prefix_tsquery("HP  EliteD") == "'hp':* & 'elited':*"
    # Punctuation never reaches the tsquery parser; hyphenated references
    # search each part (both are lexemes of the indexed text).
    assert prefix_tsquery("i5-8500 (G2) & co!") == "'i5':* & '8500':* & 'g2':* & 'co':*"
    assert prefix_tsquery("  ?! ") == ""


@pytest.mark.asyncio
async def test_search_matches_the_beginning_of_a_word(db_session: AsyncSession) -> None:
    """« 242 » finds 242S9 and « EliteD » EliteDesk: the storefront search is
    a prefix search, not a whole-word one (recette du 02/10/2026)."""
    await _seed(db_session)

    assert _names(await crud_product.search_products(db_session, q="25")) == {
        "HP 250 (B)",
        "HP 255",
    }
    assert _names(await crud_product.search_products(db_session, q="vost")) == {
        "Dell Vostro"
    }
    assert _names(await crud_product.search_products(db_session, q="hp 25")) == {
        "HP 250 (B)",
        "HP 255",
    }
    assert _names(await crud_product.search_products(db_session, q="zzz")) == set()
    # Only punctuation: no text filter rather than an SQL error.
    assert (await crud_product.search_products(db_session, q="?!"))["count"] >= 3


@pytest.mark.asyncio
async def test_a_parent_is_found_through_what_its_variants_change(
    db_session: AsyncSession,
) -> None:
    """« Je cherche un i7 » : the machine is an i5 whose variant is an i7. The
    listed entry is the parent, so the variant's name, option values and
    characteristics (``product_specs``) find it — an inactive variant's do
    not."""
    seeded = await _seed(db_session)
    laptops = seeded["laptops"]
    parent = _product("PC HP EliteDesk 800", "180000", category_id=laptops.id)
    parent.has_variants = True
    db_session.add(parent)
    await db_session.flush()
    i7 = _product("PC HP EliteDesk 800 — i7", "210000", category_id=laptops.id)
    i7.parent_product_id = parent.id
    i7.variant_options = {"Processeur": "i7"}
    retired = _product("PC HP EliteDesk 800 — Xeon", "250000", category_id=laptops.id)
    retired.parent_product_id = parent.id
    retired.variant_options = {"Processeur": "Xeon"}
    retired.is_active = False
    db_session.add_all([i7, retired])
    await db_session.flush()
    db_session.add_all(
        [
            ProductSpec(product_id=parent.id, spec_key="cpu", value_text="i5"),
            ProductSpec(product_id=i7.id, spec_key="cpu", value_text="i7"),
            ProductSpec(product_id=retired.id, spec_key="cpu", value_text="xeon"),
        ]
    )
    await db_session.commit()
    await refresh_sale_prices(db_session)

    # The text search: the variant's name / option value finds the parent,
    # which is listed alone (variants are never rows of their own).
    by_text = await crud_product.search_products(db_session, q="i7")
    assert _names(by_text) == {"PC HP EliteDesk 800"}
    assert _names(await crud_product.search_products(db_session, q="xeon")) == set()

    # The spec filter: the parent's own value and the variant's both match.
    assert _names(
        await crud_product.search_products(db_session, specs={"cpu": "i7"})
    ) == {"PC HP EliteDesk 800"}
    assert _names(
        await crud_product.search_products(db_session, specs={"cpu": "i5"})
    ) == {"PC HP EliteDesk 800"}
    assert (
        _names(await crud_product.search_products(db_session, specs={"cpu": "xeon"}))
        == set()
    )
