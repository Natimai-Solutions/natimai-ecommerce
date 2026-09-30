"""Integration: variants end to end (real Postgres).

A variant is a product row under its parent: the admin adds it, the parent
becomes the listed entry showing the cheapest variant, the listings and the
search hide the variants, the parent's « en stock » follows its variants'
stock, and the cart refuses the parent while it accepts a variant.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import (
    VariantCreateRequest,
    admin_create_product,
    admin_create_variant,
    admin_deactivate_variant,
    admin_list_variants,
)
from app.api.routes.cart import _get_active_product_or_404
from app.api.routes.product_catalog import get_product_variants
from app.core.errors import AppError
from app.features.inventory.models.inventory import Inventory
from app.features.product.crud.product import crud_product
from app.features.product.models.product import PricingMode, Product, ProductCreate
from app.features.user.models.user import User
from app.tasks.pricing_tasks import refresh_sale_prices


async def _admin(session: AsyncSession) -> User:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:6]}@test.local",
        is_active=True,
        is_superuser=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return admin


async def _fresh(session: AsyncSession, user: User) -> User:
    await session.refresh(user)
    return user


@pytest.mark.asyncio
async def test_variants_are_sold_and_listed_through_their_parent(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    parent = await admin_create_product(
        session=db_session,
        current_user=admin,
        payload=ProductCreate(
            name="T-shirt Natimai",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("0"),
        ),
    )
    parent_id = parent.id

    medium = await admin_create_variant(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        payload=VariantCreateRequest(
            options={"Taille": "M", "Couleur": "Noir"},
            supplier_sku="TS-M-NOIR",
            base_price=Decimal("2900"),
        ),
    )
    large = await admin_create_variant(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        payload=VariantCreateRequest(
            options={"Taille": "L", "Couleur": "Noir"},
            supplier_sku="TS-L-NOIR",
            base_price=Decimal("3100"),
        ),
    )
    assert medium.name == "T-shirt Natimai — M / Noir"
    assert medium.parent_product_id == parent_id
    assert medium.pricing_mode == PricingMode.FIXED

    with pytest.raises(AppError) as duplicate:
        await admin_create_variant(
            session=db_session,
            current_user=await _fresh(db_session, admin),
            product_id=parent_id,
            payload=VariantCreateRequest(options={"Taille": "M", "Couleur": "Noir"}),
        )
    assert duplicate.value.code == "product.variant.duplicate"

    # The parent is the listed entry: has_variants, cheapest price.
    parent_row = await db_session.get(Product, parent_id)
    assert parent_row is not None
    await db_session.refresh(parent_row)
    assert parent_row.has_variants is True
    assert parent_row.sale_price_cached == Decimal("2900.00")

    # Warehouse stock on the M only: the parent shows as in stock through it.
    db_session.add(
        Inventory(
            product_id=medium.id,
            place_id=None,
            quantity=Decimal("4"),
            compute_from_movements=False,
        )
    )
    await db_session.commit()
    await refresh_sale_prices(db_session)

    listed = await crud_product.search_products(db_session, group_offers=False)
    names = {p.name for p in listed["data"]}
    assert "T-shirt Natimai" in names
    assert not any(" — " in name for name in names)  # variants never listed alone
    in_stock = await crud_product.search_products(
        db_session, in_stock=True, group_offers=False
    )
    assert {p.name for p in in_stock["data"]} == {"T-shirt Natimai"}
    # Its variants' warehouse stock puts the parent « en stock chez nous ».
    local = await crud_product.search_products(
        db_session, stock="local", group_offers=False
    )
    assert {p.name for p in local["data"]} == {"T-shirt Natimai"}
    supplier = await crud_product.search_products(
        db_session, stock="supplier", group_offers=False
    )
    assert "T-shirt Natimai" not in {p.name for p in supplier["data"]}

    # The product page: axes and variants with their stock.
    page = await get_product_variants(
        session=db_session, product_id=parent_id, current_user=None
    )
    assert page.axes == ["Taille", "Couleur"]
    by_name = {v.name: v for v in page.variants}
    assert by_name["T-shirt Natimai — M / Noir"].available_quantity == Decimal("4")
    assert by_name["T-shirt Natimai — L / Noir"].available_quantity == Decimal("0")

    # The cart refuses the parent, accepts a variant.
    with pytest.raises(AppError) as refused:
        await _get_active_product_or_404(db_session, product_id=parent_id)
    assert refused.value.code == "cart.product.has_variants"
    sellable = await _get_active_product_or_404(db_session, product_id=medium.id)
    assert sellable.base_price == Decimal("2900.00")

    # Retiring the cheapest variant moves the parent's price to the next one.
    await admin_deactivate_variant(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        variant_id=medium.id,
    )
    parent_row = await db_session.get(Product, parent_id)
    assert parent_row is not None
    await db_session.refresh(parent_row)
    assert parent_row.has_variants is True
    assert parent_row.sale_price_cached == Decimal("3100.00")
    admin_view = await admin_list_variants(
        session=db_session,
        _current_user=await _fresh(db_session, admin),
        product_id=parent_id,
    )
    assert len(admin_view.variants) == 2  # inactive ones stay visible to the admin
    assert (
        len(
            (
                await get_product_variants(
                    session=db_session, product_id=parent_id, current_user=None
                )
            ).variants
        )
        == 1
    )
    assert large.id in {v.id for v in admin_view.variants}
