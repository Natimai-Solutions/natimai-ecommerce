"""Prices per customer group (real database).

The reference price is the default group's (Particulier). A group's discount
applies to every article; a price typed for the group on an article wins.
Visitors pay the reference; the cart charges what the storefront shows; and
the stored reference price of a fixed-price article is never overwritten.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_product import (
    GroupPriceInput,
    GroupPricesUpdate,
    MarginPreviewRequest,
    preview_margin,
    set_group_prices,
)
from app.api.routes.cart import add_cart_item
from app.api.routes.product_catalog import get_featured_products, search_products
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import CartItemAddRequest
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductSearchRequest,
)
from app.features.product.services.group_pricing import apply_discount
from app.features.user.models.user import User


async def _setup(session: AsyncSession) -> dict[str, Any]:
    particulier = PriceGroup(
        code="particulier",
        label="Particulier",
        default=True,
        margin_rate_pct=Decimal("30"),
    )
    pro = PriceGroup(
        code="pro",
        label="Professionnel",
        discount_pct=Decimal("10"),
        margin_rate_pct=Decimal("0"),
    )
    admin_group = PriceGroup(
        code="public", label="Administration", discount_pct=Decimal("0")
    )
    session.add_all([particulier, pro, admin_group])
    await session.flush()
    casque = Product(
        name="Casque",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("11600"),
        cost_amount=Decimal("6000"),
        is_featured=True,
        is_enriched=True,
        weight=1.0,
        customs_rate_pct=Decimal("0"),
    )
    clavier = Product(
        name="Clavier",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("5000"),
        is_featured=True,
        is_enriched=True,
        weight=1.0,
        customs_rate_pct=Decimal("0"),
    )
    session.add_all([casque, clavier])
    await session.flush()
    users = {}
    for key, group in (("pro", pro), ("public", admin_group), ("particulier", None)):
        user = User(
            email=f"{key}+{uuid.uuid4().hex[:6]}@t.local",
            hashed_password="x",
            is_active=True,
            price_group_id=group.id if group else None,
        )
        session.add(user)
        await session.flush()
        users[key] = user.id
    ids = {
        "casque": casque.id,
        "clavier": clavier.id,
        "pro": pro.id,
        "public": admin_group.id,
        "users": users,
    }
    await session.commit()
    return ids


async def _user(session: AsyncSession, user_id: uuid.UUID) -> User:
    user = await session.get(User, user_id)
    assert user is not None
    return user


def test_discount_rounds_to_the_cent() -> None:
    assert apply_discount(Decimal("11600"), Decimal("10")) == Decimal("10440.00")
    assert apply_discount(Decimal("999"), Decimal("12.5")) == Decimal("874.13")
    assert apply_discount(Decimal("100"), Decimal("0")) == Decimal("100")


@pytest.mark.asyncio
async def test_each_group_sees_its_price(db_session: AsyncSession) -> None:
    ids = await _setup(db_session)
    admin = cast(Any, User(email="a@t.local", is_superuser=True, hashed_password="x"))
    await set_group_prices(
        ids["casque"],
        GroupPricesUpdate(
            prices=[
                GroupPriceInput(price_group_id=ids["public"], price=Decimal("9900"))
            ]
        ),
        cast(Any, db_session),
        admin,
    )

    async def featured(user: Any) -> dict[str, Decimal]:
        listing = await get_featured_products(
            session=cast(Any, db_session), limit=10, current_user=user
        )
        return {p.name: p.base_price for p in listing.data}

    visitor = await featured(None)
    assert visitor == {"Casque": Decimal("11600.00"), "Clavier": Decimal("5000.00")}
    particulier = await featured(await _user(db_session, ids["users"]["particulier"]))
    assert particulier == visitor
    # Professionnel: −10 % on every article.
    pro = await featured(await _user(db_session, ids["users"]["pro"]))
    assert pro == {"Casque": Decimal("10440.00"), "Clavier": Decimal("4500.00")}
    # Administration: its typed price on the headset, the reference elsewhere.
    public = await featured(await _user(db_session, ids["users"]["public"]))
    assert public == {"Casque": Decimal("9900"), "Clavier": Decimal("5000.00")}

    search = await search_products(
        session=cast(Any, db_session),
        payload=ProductSearchRequest(limit=10),
        current_user=await _user(db_session, ids["users"]["pro"]),
    )
    assert {p.name: p.base_price for p in search.data}["Casque"] == Decimal("10440.00")


@pytest.mark.asyncio
async def test_the_cart_charges_the_group_price_and_keeps_the_reference(
    db_session: AsyncSession,
) -> None:
    ids = await _setup(db_session)
    pro_id = ids["users"]["pro"]
    await add_cart_item(
        session=cast(Any, db_session),
        current_user=await _user(db_session, pro_id),
        payload=CartItemAddRequest(product_id=ids["casque"], quantity=2),
    )
    cart = await crud_cart.get_active_cart_by_user(session=db_session, user_id=pro_id)
    assert cart is not None
    items = await crud_cart_item.get_by_cart_id(session=db_session, cart_id=cart.id)
    assert [(i.unit_price, i.quantity) for i in items] == [(Decimal("10440.00"), 2)]

    # The fixed reference price stored on the article is untouched.
    db_session.expire_all()
    casque = await db_session.get(Product, ids["casque"])
    assert casque is not None and casque.base_price == Decimal("11600.00")


@pytest.mark.asyncio
async def test_the_form_shows_the_margin_of_each_group(
    db_session: AsyncSession,
) -> None:
    ids = await _setup(db_session)
    admin = cast(Any, User(email="a@t.local", is_superuser=True, hashed_password="x"))
    preview = await preview_margin(
        MarginPreviewRequest(
            product_id=ids["casque"], group_prices={ids["public"]: Decimal("9280")}
        ),
        cast(Any, db_session),
        admin,
    )
    lines = {line.label: line for line in preview.groups}
    assert list(lines) == ["Particulier", "Administration", "Professionnel"]
    # No tax rate in this database: HT = TTC.
    assert lines["Particulier"].price == Decimal("11600.00")
    assert lines["Particulier"].margin_amount == Decimal("5600.00")
    assert lines["Professionnel"].price == Decimal("10440.00")
    assert lines["Professionnel"].margin_amount == Decimal("4440.00")
    assert lines["Administration"].typed_price == Decimal("9280")
    assert lines["Administration"].margin_amount == Decimal("3280.00")


@pytest.mark.asyncio
async def test_typed_prices_are_set_and_cleared(db_session: AsyncSession) -> None:
    ids = await _setup(db_session)
    admin = cast(Any, User(email="a@t.local", is_superuser=True, hashed_password="x"))
    stored = await set_group_prices(
        ids["clavier"],
        GroupPricesUpdate(
            prices=[
                GroupPriceInput(price_group_id=ids["pro"], price=Decimal("4200")),
                GroupPriceInput(price_group_id=ids["public"], price=Decimal("4100")),
            ]
        ),
        cast(Any, db_session),
        admin,
    )
    assert {s.price_group_id: s.price for s in stored} == {
        ids["pro"]: Decimal("4200.00"),
        ids["public"]: Decimal("4100.00"),
    }
    stored = await set_group_prices(
        ids["clavier"],
        GroupPricesUpdate(
            prices=[
                GroupPriceInput(price_group_id=ids["pro"], price=None),
                GroupPriceInput(price_group_id=ids["public"], price=Decimal("4000")),
            ]
        ),
        cast(Any, db_session),
        admin,
    )
    assert {s.price_group_id: s.price for s in stored} == {
        ids["public"]: Decimal("4000.00")
    }
