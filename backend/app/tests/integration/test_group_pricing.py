"""Prices per customer group (real database).

The reference price is the default group's (Particulier). A group's discount
applies to every article; a price typed for the group on an article wins.
Visitors pay the reference; the cart charges what the storefront shows; and
the stored reference price of a fixed-price article is never overwritten.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from pydantic import ValidationError
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_price_groups import update_price_group
from app.api.routes.admin_product import (
    GroupPriceInput,
    GroupPricesUpdate,
    MarginPreviewRequest,
    preview_margin,
    set_group_prices,
)
from app.api.routes.cart import add_cart_item
from app.api.routes.product_catalog import get_featured_products, search_products
from app.core.errors import AppError
from app.features.cart.crud.cart import crud_cart, crud_cart_item
from app.features.cart.models.cart import CartItemAddRequest
from app.features.discount.models import Discount, DiscountTarget, DiscountType
from app.features.discount.services.checkout_discount import (
    DiscountRefused,
    resolve_coupon,
)
from app.features.product.models.category import Category
from app.features.product.models.price_group import PriceGroup, PriceGroupUpdate
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


@pytest.mark.asyncio
async def test_a_free_or_duplicated_group_price_is_refused(
    db_session: AsyncSession,
) -> None:
    ids = await _setup(db_session)
    admin = cast(Any, User(email="a@t.local", is_superuser=True, hashed_password="x"))
    # 0 would sell the article for free to that group.
    with pytest.raises(ValidationError):
        GroupPriceInput(price_group_id=ids["pro"], price=Decimal("0"))
    # The same group twice in one grid: refused, nothing written.
    with pytest.raises(AppError) as refused:
        await set_group_prices(
            ids["clavier"],
            GroupPricesUpdate(
                prices=[
                    GroupPriceInput(price_group_id=ids["pro"], price=Decimal("100")),
                    GroupPriceInput(price_group_id=ids["pro"], price=Decimal("120")),
                ]
            ),
            cast(Any, db_session),
            admin,
        )
    assert refused.value.code == "price_group.duplicate"


@pytest.mark.asyncio
async def test_the_default_group_never_carries_a_discount(
    db_session: AsyncSession,
) -> None:
    ids = await _setup(db_session)
    admin = cast(Any, SimpleNamespace(id=None, is_superuser=True))
    # Promoting a discounted group to default would discount every visitor.
    with pytest.raises(AppError) as refused:
        await update_price_group(
            ids["pro"], PriceGroupUpdate(default=True), cast(Any, db_session), admin
        )
    assert refused.value.code == "price_group.default_discount"
    # Dropping the discount in the same call is fine.
    updated = await update_price_group(
        ids["pro"],
        PriceGroupUpdate(default=True, discount_pct=Decimal("0")),
        cast(Any, db_session),
        admin,
    )
    assert updated.default is True and updated.discount_pct == 0


# --- Promotions: the best price wins -----------------------------------------


def _promotion(**fields: Any) -> Discount:
    return Discount(
        discount_type=DiscountType.PROMOTION,
        name=fields.pop("name", "Promo"),
        target=fields.pop("target", DiscountTarget.PRODUCT),
        **fields,
    )


@pytest.mark.asyncio
async def test_a_promotion_never_stacks_on_the_group_price(
    db_session: AsyncSession,
) -> None:
    ids = await _setup(db_session)
    admin = cast(Any, User(email="a@t.local", is_superuser=True, hashed_password="x"))
    await set_group_prices(
        ids["casque"],
        GroupPricesUpdate(
            prices=[
                GroupPriceInput(price_group_id=ids["public"], price=Decimal("9000"))
            ]
        ),
        cast(Any, db_session),
        admin,
    )
    now = datetime.now(UTC)
    db_session.add_all(
        [
            _promotion(
                name="Rentrée −20 %",
                product_id=ids["casque"],
                percentage=Decimal("20"),
                start_date=now - timedelta(days=1),
                end_date=now + timedelta(days=7),
            ),
            # Over or not started: ignored.
            _promotion(
                name="Passée",
                product_id=ids["clavier"],
                percentage=Decimal("50"),
                end_date=now - timedelta(days=1),
            ),
            _promotion(
                name="À venir",
                product_id=ids["clavier"],
                percentage=Decimal("50"),
                start_date=now + timedelta(days=1),
            ),
        ]
    )
    await db_session.commit()

    async def featured(user: Any) -> dict[str, Any]:
        listing = await get_featured_products(
            session=cast(Any, db_session), limit=10, current_user=user
        )
        return {p.name: p for p in listing.data}

    visitor = await featured(None)
    assert visitor["Casque"].base_price == Decimal("9280.00")
    assert visitor["Casque"].regular_price == Decimal("11600.00")
    assert visitor["Casque"].promotion_name == "Rentrée −20 %"
    assert visitor["Clavier"].base_price == Decimal("5000.00")
    assert visitor["Clavier"].regular_price is None

    # Professionnel (−10 % → 10 440): the promotion is better, no stacking.
    pro = await featured(await _user(db_session, ids["users"]["pro"]))
    assert pro["Casque"].base_price == Decimal("9280.00")
    assert pro["Casque"].regular_price == Decimal("10440.00")
    assert pro["Clavier"].base_price == Decimal("4500.00")

    # Administration: its typed price (9 000) beats the promotion.
    public = await featured(await _user(db_session, ids["users"]["public"]))
    assert public["Casque"].base_price == Decimal("9000")
    assert public["Casque"].promotion_name is None

    # The cart charges the best price.
    pro_id = ids["users"]["pro"]
    await add_cart_item(
        session=cast(Any, db_session),
        current_user=await _user(db_session, pro_id),
        payload=CartItemAddRequest(product_id=ids["casque"], quantity=1),
    )
    cart = await crud_cart.get_active_cart_by_user(session=db_session, user_id=pro_id)
    assert cart is not None
    items = await crud_cart_item.get_by_cart_id(session=db_session, cart_id=cart.id)
    assert [i.unit_price for i in items] == [Decimal("9280.00")]


@pytest.mark.asyncio
async def test_a_category_promotion_in_amount(db_session: AsyncSession) -> None:
    ids = await _setup(db_session)
    category = Category(name=f"Écrans {uuid.uuid4().hex[:4]}")
    db_session.add(category)
    await db_session.flush()
    clavier = await db_session.get(Product, ids["clavier"])
    assert clavier is not None
    clavier.category_id = category.id
    db_session.add(clavier)
    db_session.add(
        _promotion(
            name="−1 000 F sur la catégorie",
            target=DiscountTarget.CATEGORY,
            category_id=category.id,
            amount=Decimal("1000"),
        )
    )
    await db_session.commit()
    listing = await get_featured_products(
        session=cast(Any, db_session), limit=10, current_user=None
    )
    prices = {p.name: p.base_price for p in listing.data}
    assert prices["Clavier"] == Decimal("4000.00")
    assert prices["Casque"] == Decimal("11600.00")


@pytest.mark.asyncio
async def test_a_non_stackable_code_skips_promoted_articles(
    db_session: AsyncSession,
) -> None:
    ids = await _setup(db_session)
    db_session.add_all(
        [
            _promotion(product_id=ids["casque"], percentage=Decimal("20")),
            Discount(
                name="Dix",
                code="DIX",
                discount_type=DiscountType.COUPON,
                percentage=Decimal("10"),
                target=DiscountTarget.ORDER,
                applies_to_promoted=False,
            ),
        ]
    )
    await db_session.commit()
    products = {
        ids["casque"]: SimpleNamespace(id=ids["casque"], category_id=None),
        ids["clavier"]: SimpleNamespace(id=ids["clavier"], category_id=None),
    }

    def line(product_id: uuid.UUID, price: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=uuid.uuid4(),
            product_id=product_id,
            unit_price=Decimal(price),
            quantity=1,
        )

    applied = await resolve_coupon(
        db_session,
        code="dix",
        user_id=ids["users"]["pro"],
        items=[line(ids["casque"], "9280"), line(ids["clavier"], "5000")],
        products_by_id=products,
        currency="XPF",
    )
    assert applied.amount == Decimal("500")  # 10 % of the keyboard only

    with pytest.raises(DiscountRefused) as refused:
        await resolve_coupon(
            db_session,
            code="dix",
            user_id=ids["users"]["pro"],
            items=[line(ids["casque"], "9280")],
            products_by_id=products,
            currency="XPF",
        )
    assert refused.value.reason == "promoted_only"


async def _gift_card(session: AsyncSession) -> uuid.UUID:
    card = Product(
        name="Carte cadeau 10 000",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("10000"),
        gift_card_amount=Decimal("10000"),
        is_featured=True,
        is_enriched=True,
        weight=0.0,
        customs_rate_pct=Decimal("0"),
    )
    session.add(card)
    card_id = card.id
    await session.commit()
    return card_id


@pytest.mark.asyncio
async def test_a_gift_card_takes_no_group_price_nor_promotion(
    db_session: AsyncSession,
) -> None:
    """Audit 2026-11, S3: a card is issued at its face value once paid. Sold
    10 % off to a group (or under a promotion), it was 1 000 F of store
    credit for nothing, as many times as wanted."""
    ids = await _setup(db_session)
    card_id = await _gift_card(db_session)
    db_session.add(_promotion(product_id=card_id, percentage=Decimal("20")))
    await db_session.commit()

    pro_id = ids["users"]["pro"]  # group −10 %
    listing = await get_featured_products(
        session=cast(Any, db_session),
        limit=10,
        current_user=await _user(db_session, pro_id),
    )
    shown = {p.name: p for p in listing.data}
    assert shown["Carte cadeau 10 000"].base_price == Decimal("10000")
    assert shown["Carte cadeau 10 000"].promotion_name is None
    assert shown["Clavier"].base_price == Decimal("4500.00")  # others unchanged

    await add_cart_item(
        session=cast(Any, db_session),
        current_user=await _user(db_session, pro_id),
        payload=CartItemAddRequest(product_id=card_id, quantity=1),
    )
    cart = await crud_cart.get_active_cart_by_user(session=db_session, user_id=pro_id)
    assert cart is not None
    items = await crud_cart_item.get_by_cart_id(session=db_session, cart_id=cart.id)
    assert [i.unit_price for i in items] == [Decimal("10000")]


@pytest.mark.asyncio
async def test_a_promo_code_never_covers_a_gift_card(db_session: AsyncSession) -> None:
    ids = await _setup(db_session)
    card_id = await _gift_card(db_session)
    db_session.add(
        Discount(
            name="Vingt",
            code="VINGT",
            discount_type=DiscountType.COUPON,
            percentage=Decimal("20"),
            target=DiscountTarget.ORDER,
        )
    )
    await db_session.commit()
    products = {
        card_id: SimpleNamespace(
            id=card_id, category_id=None, gift_card_amount=Decimal("10000")
        ),
        ids["clavier"]: SimpleNamespace(
            id=ids["clavier"], category_id=None, gift_card_amount=None
        ),
    }

    def line(product_id: uuid.UUID, price: str) -> SimpleNamespace:
        return SimpleNamespace(
            id=uuid.uuid4(),
            product_id=product_id,
            unit_price=Decimal(price),
            quantity=1,
        )

    applied = await resolve_coupon(
        db_session,
        code="vingt",
        user_id=ids["users"]["pro"],
        items=[line(card_id, "10000"), line(ids["clavier"], "5000")],
        products_by_id=products,
        currency="XPF",
    )
    assert applied.amount == Decimal("1000")  # 20 % of the keyboard only

    with pytest.raises(DiscountRefused) as refused:
        await resolve_coupon(
            db_session,
            code="vingt",
            user_id=ids["users"]["pro"],
            items=[line(card_id, "10000")],
            products_by_id=products,
            currency="XPF",
        )
    assert refused.value.reason == "not_applicable"
