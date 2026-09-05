"""Integration: « autres offres » — the same item at several suppliers.

Real Postgres session. One product per source is the model; the storefront
groups siblings (same barcode, else manufacturer + part number) behind the
cheapest offer in listings and lists every offer on the product page.
"""

from __future__ import annotations

from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.product_catalog import get_product_offers, search_products
from app.core.errors import AppError
from app.features.integrations.models.supplier import Supplier, SupplierKind
from app.features.product.crud.product import crud_product
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductSearchRequest,
)


def _product(
    name: str,
    *,
    supplier: str,
    price: str,
    qty: str = "5",
    ean: str | None = "0036000291452",
    manufacturer: str | None = "Logi",
    mpn: str | None = "K120",
    enriched: bool = True,
) -> Product:
    return Product(
        name=name,
        supplier_name=supplier,
        supplier_sku=f"{supplier}-{name}",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal(price),
        supplier_quantity=Decimal(qty),
        ean=ean,
        manufacturer=manufacturer,
        vendor_part_number=mpn,
        is_enriched=enriched,
        is_supplier_managed=True,
    )


async def _seed(db_session: AsyncSession) -> dict[str, Product]:
    db_session.add_all(
        [
            Supplier(code="tahiti", name="Distributeur Tahiti", is_domestic=True),
            Supplier(code="france", name="Grossiste France", kind=SupplierKind.FILE),
        ]
    )
    products = {
        "local": _product("Clavier (local)", supplier="tahiti", price="6500"),
        "import": _product("Clavier (import)", supplier="france", price="5200"),
        "zero_ean": _product(
            "Clavier (zéro perdu)", supplier="france", price="5900", ean="36000291452"
        ),
        "mpn_only": _product(
            "Clavier (sans EAN)", supplier="tahiti", price="7000", ean=None
        ),
        "hidden": _product(
            "Clavier (non enrichi)", supplier="france", price="100", enriched=False
        ),
        "other": _product(
            "Souris", supplier="tahiti", price="1500", ean="3663970012345", mpn="M185"
        ),
    }
    db_session.add_all(products.values())
    await db_session.commit()
    for product in products.values():
        await db_session.refresh(product)
    return products


@pytest.mark.asyncio
async def test_offers_lists_every_sibling_cheapest_first(
    db_session: AsyncSession,
) -> None:
    products = await _seed(db_session)

    response = await get_product_offers(
        product_id=products["local"].id, session=db_session, current_user=None
    )

    assert response.identity_key == "gtin:36000291452"
    assert [o.name for o in response.offers] == [
        "Clavier (import)",
        "Clavier (zéro perdu)",
        "Clavier (local)",
        "Clavier (sans EAN)",
    ]
    assert response.cheapest_product_id == products["import"].id
    current = next(o for o in response.offers if o.is_current)
    assert current.product_id == products["local"].id
    assert current.supplier_label == "Distributeur Tahiti"
    assert current.is_domestic is True
    assert current.sale_price == Decimal("6500.00")
    imported = response.offers[0]
    assert imported.is_domestic is False
    assert imported.in_stock is True


@pytest.mark.asyncio
async def test_offers_ignore_products_with_a_different_barcode(
    db_session: AsyncSession,
) -> None:
    products = await _seed(db_session)

    response = await get_product_offers(
        product_id=products["other"].id, session=db_session, current_user=None
    )

    assert [o.name for o in response.offers] == ["Souris"]
    assert response.cheapest_product_id == products["other"].id


@pytest.mark.asyncio
async def test_offers_of_an_unpublished_product_are_404(
    db_session: AsyncSession,
) -> None:
    products = await _seed(db_session)

    with pytest.raises(AppError) as exc_info:
        await get_product_offers(
            product_id=products["hidden"].id, session=db_session, current_user=None
        )
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_search_groups_siblings_behind_the_cheapest(
    db_session: AsyncSession,
) -> None:
    products = await _seed(db_session)

    grouped = await search_products(
        session=db_session, payload=ProductSearchRequest(q="clavier")
    )
    assert grouped.count == 2  # one keyboard by barcode + the barcode-less one
    by_id = {p.id: p for p in grouped.data}
    assert products["import"].id in by_id
    assert by_id[products["import"].id].offers_count == 3
    assert by_id[products["mpn_only"].id].offers_count == 1

    flat = await search_products(
        session=db_session,
        payload=ProductSearchRequest(q="clavier", group_offers=False),
    )
    assert flat.count == 4
    assert all(p.offers_count == 1 for p in flat.data)


@pytest.mark.asyncio
async def test_find_offers_matches_by_part_number_without_barcode(
    db_session: AsyncSession,
) -> None:
    products = await _seed(db_session)

    siblings = await crud_product.find_offers(db_session, products["mpn_only"])

    # No barcode of its own: manufacturer + part number matches all keyboards.
    assert {p.name for p in siblings} == {
        "Clavier (local)",
        "Clavier (import)",
        "Clavier (zéro perdu)",
    }
