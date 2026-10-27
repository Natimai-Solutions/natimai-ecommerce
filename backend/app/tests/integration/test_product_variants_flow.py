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
    admin_update_product,
)
from app.api.routes.cart import _get_active_product_or_404
from app.api.routes.product_catalog import get_product_variants
from app.core.errors import AppError
from app.features.inventory.models.inventory import Inventory
from app.features.inventory.services.availability import publish_with_availability
from app.features.product.crud.product import crud_product
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductCreate,
    ProductUpdate,
)
from app.features.product.services.variants import list_variants
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


async def admin_update_variant_cost(
    session: AsyncSession, admin: User, variant_id: uuid.UUID
) -> None:
    """Give a variant a purchase cost, so it carries a margin to roll up."""
    await admin_update_product(
        session=session,
        current_user=await _fresh(session, admin),
        product_id=variant_id,
        payload=ProductUpdate(cost_amount=Decimal("1000")),
    )


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

    # Editing the parent itself keeps the roll-up (price and margin of the
    # cheapest variant), never its own — absent — cost.
    await admin_update_variant_cost(db_session, admin, medium.id)
    await admin_update_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        payload=ProductUpdate(description="Coton bio"),
    )
    parent_row = await db_session.get(Product, parent_id)
    assert parent_row is not None
    await db_session.refresh(parent_row)
    assert parent_row.sale_price_cached == Decimal("2900.00")
    assert parent_row.unit_cost_cached == Decimal("1000.00")
    assert parent_row.margin_cached is not None and parent_row.margin_cached > 0

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


@pytest.mark.asyncio
async def test_a_variant_supplement_follows_the_parent_price(
    db_session: AsyncSession,
) -> None:
    """R9 / T6: « i5 à 30 000, i7 à + 10 000 » — the i7 price is derived from
    the parent's and recomputed when the parent price changes; the parent
    keeps its reference price instead of the cheapest variant."""
    admin = await _admin(db_session)
    parent = await admin_create_product(
        session=db_session,
        current_user=admin,
        payload=ProductCreate(
            name="PC fixe", pricing_mode=PricingMode.FIXED, base_price=Decimal("30000")
        ),
    )
    parent_id = parent.id
    i5 = await admin_create_variant(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        payload=VariantCreateRequest(
            options={"Processeur": "i5"}, price_extra=Decimal("0")
        ),
    )
    i7 = await admin_create_variant(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        payload=VariantCreateRequest(
            options={"Processeur": "i7"}, price_extra=Decimal("10000")
        ),
    )
    assert (i5.base_price, i7.base_price) == (Decimal("30000.00"), Decimal("40000.00"))
    assert i7.price_extra == Decimal("10000.00")

    parent_row = await db_session.get(Product, parent_id)
    assert parent_row is not None
    assert parent_row.base_price == Decimal("30000.00")  # reference, not rolled up
    assert parent_row.sale_price_cached == Decimal("30000.00")  # « à partir de »

    # The parent price moves: both supplements follow.
    await admin_update_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        payload=ProductUpdate(base_price=Decimal("32000")),
    )
    prices = {
        v.variant_options["Processeur"]: (v.base_price, v.sale_price_cached)
        for v in await list_variants(db_session, parent_id)
        if v.variant_options
    }
    assert prices == {
        "i5": (Decimal("32000.00"), Decimal("32000.00")),
        "i7": (Decimal("42000.00"), Decimal("42000.00")),
    }

    # Changing the supplement re-derives the price; dropping it frees the price.
    changed = await admin_update_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=i7.id,
        payload=ProductUpdate(price_extra=Decimal("5000")),
    )
    assert changed.base_price == Decimal("37000.00")
    freed = await admin_update_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=i7.id,
        payload=ProductUpdate(price_extra=None, base_price=Decimal("45000")),
    )
    assert (freed.price_extra, freed.base_price) == (None, Decimal("45000.00"))


@pytest.mark.asyncio
async def test_optional_variants_keep_the_base_product_sellable(
    db_session: AsyncSession,
) -> None:
    """« PC à 18 000, i7 à + 3 000 » with the i5 machine sold as is: the
    parent keeps its own price and stock, the cart accepts it, and the
    variant is an option on top. Switching the rule off brings the entry-only
    behaviour back (cheapest variant, variants' stock, cart refusal)."""
    admin = await _admin(db_session)
    parent = await admin_create_product(
        session=db_session,
        current_user=admin,
        payload=ProductCreate(
            name="PC HP EliteDesk",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("18000"),
            variants_optional=True,
        ),
    )
    parent_id = parent.id
    i7 = await admin_create_variant(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        payload=VariantCreateRequest(
            options={"Processeur": "i7"}, base_price=Decimal("12000")
        ),
    )
    db_session.add_all(
        [
            Inventory(
                product_id=parent_id,
                place_id=None,
                quantity=Decimal("1"),
                compute_from_movements=False,
            ),
            Inventory(
                product_id=i7.id,
                place_id=None,
                quantity=Decimal("2"),
                compute_from_movements=False,
            ),
        ]
    )
    await db_session.commit()
    await refresh_sale_prices(db_session)

    # Priced as itself, not « à partir de » the (cheaper) variant.
    parent_row = await db_session.get(Product, parent_id)
    assert parent_row is not None
    await db_session.refresh(parent_row)
    assert parent_row.has_variants is True
    assert parent_row.sale_price_cached == Decimal("18000.00")

    # Sold as is, with its own stock (the one the checkout reserves).
    sold = await _get_active_product_or_404(db_session, product_id=parent_id)
    assert sold.base_price == Decimal("18000.00")
    (published,) = await publish_with_availability(db_session, [parent_row])
    assert published.variants_count == 1
    assert published.available_quantity == Decimal("1")
    listed = await crud_product.search_products(
        db_session, stock="local", group_offers=False
    )
    assert "PC HP EliteDesk" in {p.name for p in listed["data"]}

    # Back to the entry-only rule: cheapest variant, variants' stock, no sale.
    await admin_update_product(
        session=db_session,
        current_user=await _fresh(db_session, admin),
        product_id=parent_id,
        payload=ProductUpdate(variants_optional=False),
    )
    parent_row = await db_session.get(Product, parent_id)
    assert parent_row is not None
    await db_session.refresh(parent_row)
    assert parent_row.sale_price_cached == Decimal("12000.00")
    (published,) = await publish_with_availability(db_session, [parent_row])
    assert published.available_quantity == Decimal("3")
    with pytest.raises(AppError) as refused:
        await _get_active_product_or_404(db_session, product_id=parent_id)
    assert refused.value.code == "cart.product.has_variants"
