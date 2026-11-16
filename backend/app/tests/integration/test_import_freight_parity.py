"""Integration (real DB): the import freight is in the price, everywhere.

Functional audit of November 2026: the product page showed the price of the
chosen import mode, freight included; the catalogue, the cart and the order
priced with no route — no freight — and the checkout skipped the import leg
as « already in the price ». The freight was billed nowhere.

One price now: no mode chosen = the default import route; a line carries the
mode chosen on the page and is priced on that route."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import add_cart_item, replace_my_cart_items
from app.api.routes.product_catalog import get_product_shipping_modes
from app.features.cart.models.cart import CartItemAddRequest, CartReplaceRequest
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.features.product.services.pricing import PricingContext, calculate_sale_price
from app.features.shipping.models.route import ShippingRoute
from app.features.user.models.user import User


async def _seed(session: AsyncSession) -> tuple[uuid.UUID, uuid.UUID]:
    """A 2 kg imported article, air (default, 700/kg) and sea (150/kg)."""
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    origin = Place(name="Hub", type="warehouse", is_warehouse=True, country="FR")
    papeete = Place(name="Papeete", type="warehouse", is_warehouse=True, country="PF")
    session.add_all([user, origin, papeete])
    await session.flush()
    product = Product(
        name="Écran",
        base_price=Decimal("10000"),
        cost_amount=Decimal("10000"),
        cost_currency="XPF",
        weight=2.0,
        customs_rate_pct=Decimal("0"),
        margin_rate_pct=Decimal("0"),
    )
    session.add(product)
    for level, per_kg, default, priority in (
        ("rapide", "700", True, 1),
        ("economique", "150", False, 2),
    ):
        session.add(
            ShippingRoute(
                from_place_id=origin.id,
                to_place_id=papeete.id,
                name=f"Import {level}",
                mode="air" if default else "sea",
                service_level=level,
                customer_label=level.capitalize(),
                is_default_import=default,
                priority=priority,
                price_per_kg=Decimal(per_kg),
                route_metadata={"billing_basis": "actual_weight"},
            )
        )
    await session.flush()
    ids = (user.id, product.id)
    await session.commit()
    return ids


async def _page_prices(
    session: AsyncSession, product_id: uuid.UUID
) -> tuple[dict[str, Decimal], str | None]:
    modes = await get_product_shipping_modes(product_id, session, None)
    prices = {
        str(mode.service_level): Decimal(str(mode.sale_price))
        for mode in modes.shipping_modes
    }
    return prices, modes.default_mode


@pytest.mark.asyncio
async def test_the_catalogue_and_the_cart_bill_the_default_freight(
    db_session: AsyncSession,
) -> None:
    user_id, product_id = await _seed(db_session)
    page, default_mode = await _page_prices(db_session, product_id)
    assert default_mode == "rapide"
    assert page["rapide"] > page["economique"] > Decimal("10000")

    product = await db_session.get(Product, product_id)
    assert product is not None
    # No route asked: the default one, never « no freight ».
    assert await calculate_sale_price(db_session, product) == page["rapide"]
    context = await PricingContext.load(db_session)
    assert context.price(product) == page["rapide"]  # the listing's cached price
    # … and the cost price carries the same freight (the margin was overstated).
    assert context.unit_cost(product) == Decimal("11400.00")

    user = await db_session.get(User, user_id)
    assert user is not None
    cart = await add_cart_item(
        session=db_session,
        current_user=user,
        payload=CartItemAddRequest(product_id=product_id, quantity=1),
    )
    assert cart.items[0].unit_price == page["rapide"]
    assert cart.items[0].import_service_level == "rapide"


@pytest.mark.asyncio
async def test_a_line_is_billed_on_the_mode_chosen_on_the_page(
    db_session: AsyncSession,
) -> None:
    user_id, product_id = await _seed(db_session)
    page, _ = await _page_prices(db_session, product_id)

    async def replace(level: str | None) -> tuple[Decimal, str | None]:
        user = await db_session.get(User, user_id)
        assert user is not None
        cart = await replace_my_cart_items(
            session=db_session,
            current_user=user,
            payload=CartReplaceRequest(
                items=[
                    CartItemAddRequest(
                        product_id=product_id, quantity=2, import_service_level=level
                    )
                ]
            ),
        )
        return cart.items[0].unit_price, cart.items[0].import_service_level

    assert await replace("economique") == (page["economique"], "economique")
    assert await replace("rapide") == (page["rapide"], "rapide")
    # A mode that is not on offer falls back on the default one, freight in.
    assert await replace("teleportation") == (page["rapide"], "rapide")
