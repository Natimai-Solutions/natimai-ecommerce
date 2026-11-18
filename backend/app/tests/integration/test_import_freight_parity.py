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
from sqlmodel import col, select
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


@pytest.mark.asyncio
async def test_the_fixed_cost_of_an_import_route_is_spread_per_kg(
    db_session: AsyncSession,
) -> None:
    """Decision of 18/11/2026: the forwarder's fixed fee per shipment was
    billed nowhere (not in the article price, skipped at checkout). Spread
    over the weight of a departure at its threshold: 15 000 F over 200 kg =
    75 F per billable kg, on top of the 700 F/kg — everywhere the freight is."""
    from sqlmodel import col, select

    from app.features.shipping.services.import_routes import forget_import_routes

    user_id, product_id = await _seed(db_session)
    rapide = (
        await db_session.exec(
            select(ShippingRoute).where(col(ShippingRoute.service_level) == "rapide")
        )
    ).one()
    rapide.base_price = Decimal("15000")
    db_session.add(rapide)
    await db_session.commit()
    forget_import_routes(db_session)

    # Without the weight it is spread over, the fixed cost is not billed.
    page, _ = await _page_prices(db_session, product_id)
    assert page["rapide"] == Decimal("11400.00")

    rapide = (
        await db_session.exec(
            select(ShippingRoute).where(col(ShippingRoute.service_level) == "rapide")
        )
    ).one()
    rapide.import_fixed_basis_kg = Decimal("200")
    db_session.add(rapide)
    await db_session.commit()
    forget_import_routes(db_session)

    # 2 kg × (700 + 75) = 1 550 F of freight on a 10 000 F article.
    page, _ = await _page_prices(db_session, product_id)
    assert page["rapide"] == Decimal("11550.00")
    product = await db_session.get(Product, product_id)
    assert product is not None
    assert await calculate_sale_price(db_session, product) == page["rapide"]
    context = await PricingContext.load(db_session)
    assert context.price(product) == page["rapide"]
    assert context.unit_cost(product) == Decimal("11550.00")
    # The sea route has no fixed cost: unchanged.
    assert page["economique"] == Decimal("10300.00")

    user = await db_session.get(User, user_id)
    assert user is not None
    cart = await add_cart_item(
        session=db_session,
        current_user=user,
        payload=CartItemAddRequest(product_id=product_id, quantity=1),
    )
    assert cart.items[0].unit_price == page["rapide"]


@pytest.mark.asyncio
async def test_the_delay_shown_adds_the_supplier_lead_time(
    db_session: AsyncSession,
) -> None:
    """Functional audit D1: the delay on the product page counted the route
    only — an article ordered from the supplier waits for it first."""
    from sqlmodel import col, select

    from app.features.integrations.models.supplier import Supplier
    from app.features.inventory.models.inventory import Inventory

    _user_id, product_id = await _seed(db_session)
    product = await db_session.get(Product, product_id)
    assert product is not None
    product.supplier_name = "grossiste"
    db_session.add(product)
    db_session.add(Supplier(code="grossiste", name="Grossiste", lead_time_days=4))
    rapide = (
        await db_session.exec(
            select(ShippingRoute).where(col(ShippingRoute.service_level) == "rapide")
        )
    ).one()
    rapide.eta_days = 3
    db_session.add(rapide)
    await db_session.commit()

    modes = await get_product_shipping_modes(product_id, db_session, None)
    by_level = {m.service_level: m.eta_days for m in modes.shipping_modes}
    assert modes.supplier_lead_days == 4
    assert by_level["rapide"] == 7  # 4 days at the supplier + 3 in the air

    # In local stock it leaves with the departure: the route only.
    db_session.add(
        Inventory(
            product_id=product_id,
            quantity=Decimal("5"),
            compute_from_movements=False,
        )
    )
    await db_session.commit()
    modes = await get_product_shipping_modes(product_id, db_session, None)
    assert modes.supplier_lead_days == 0
    assert {m.service_level: m.eta_days for m in modes.shipping_modes}["rapide"] == 3


@pytest.mark.asyncio
async def test_one_freight_from_the_product_page_to_the_invoice(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Functional audit D1 and review of 17/11/2026: the freight-inclusive
    price of the mode chosen on the page is the price of the cart line, of
    the order line, and of the invoice line — one freight, billed once."""
    from typing import Any

    from app.api.routes import cart as cart_routes
    from app.api.routes.cart import checkout_my_cart
    from app.features.cart.models.cart import CheckoutRequest
    from app.features.inventory.models.inventory import Inventory
    from app.features.invoice.services.invoice_service import issue_invoice_for_order
    from app.features.order.models.order import Order
    from app.features.order.models.order_line import OrderLine

    async def nothing(*_args: Any, **_kwargs: Any) -> dict[Any, Any]:
        return {}

    monkeypatch.setattr(cart_routes, "refresh_supplier_availability", nothing)
    user_id, product_id = await _seed(db_session)
    db_session.add(
        Inventory(
            product_id=product_id, quantity=Decimal("10"), compute_from_movements=False
        )
    )
    await db_session.commit()
    page, _ = await _page_prices(db_session, product_id)
    sea_price = page["economique"]  # 10 000 + 2 kg × 150

    user = await db_session.get(User, user_id)
    assert user is not None
    cart = await replace_my_cart_items(
        session=db_session,
        current_user=user,
        payload=CartReplaceRequest(
            items=[
                CartItemAddRequest(
                    product_id=product_id, quantity=2, import_service_level="economique"
                )
            ]
        ),
    )
    assert cart.items[0].unit_price == sea_price

    user = await db_session.get(User, user_id)
    assert user is not None
    placed = await checkout_my_cart(
        db_session,
        user,
        CheckoutRequest(shipping_address="Papeete", cgv_accepted=True),
    )
    order = await db_session.get(Order, placed.order_id)
    assert order is not None
    line = (
        await db_session.exec(
            select(OrderLine).where(col(OrderLine.order_id) == placed.order_id)
        )
    ).one()
    assert line.unit_price == sea_price
    assert line.import_service_level == "economique"
    # The import leg is in the price: no shipping fee on top of it.
    assert order.shipping_fee_amount == Decimal("0")
    assert order.total_amount == sea_price * 2

    order_total = order.total_amount
    invoice = await issue_invoice_for_order(db_session, order_id=placed.order_id)
    await db_session.refresh(invoice)
    assert invoice.total_incl_tax == order_total
    invoiced = invoice.snapshot["lines"][0]
    assert Decimal(str(invoiced["quantity"])) == Decimal("2")
