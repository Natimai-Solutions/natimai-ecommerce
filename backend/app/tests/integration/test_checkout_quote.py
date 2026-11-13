"""Integration: GET /cart/me/checkout-quote returns what the checkout bills."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import _quote_checkout, get_checkout_quote
from app.core.config import settings
from app.core.errors import AppError
from app.features.cart.models.cart import Cart, CartItem, CheckoutQuoteResponse
from app.features.payment.models.payment_method import PaymentMethod
from app.features.place.models import Place
from app.features.product.models.product import Product
from app.features.shipping.models.route import ShippingRoute
from app.features.user.models.user import User


async def _seed(session: AsyncSession) -> SimpleNamespace:
    user = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    warehouse = Place(
        name="Entrepôt", type="warehouse", is_warehouse=True, country="FR"
    )
    customer = Place(name="Client", type="address")
    session.add_all([user, warehouse, customer])
    await session.flush()

    product = Product(
        name="Casque",
        base_price=Decimal("80.00"),
        cost_amount=Decimal("80.00"),
        cost_currency=settings.REFERENCE_CURRENCY,
        weight=2.0,
        customs_rate_pct=Decimal("0"),
    )
    cart = Cart(user_id=user.id, currency=settings.REFERENCE_CURRENCY)
    session.add_all([product, cart])
    await session.flush()
    item = CartItem(
        cart_id=cart.id,
        product_id=product.id,
        quantity=2,
        unit_price=Decimal("80.00"),
    )
    colissimo = ShippingRoute(
        from_place_id=warehouse.id,
        to_place_id=customer.id,
        name="Colissimo",
        mode="road",
        is_to_customer=True,
        last_leg_delivery_type="home_delivery",
        eta_days=3,
        weight_bands=[
            {"max_kg": "3", "price": "8.00"},
            {"max_kg": "10", "price": "12.00"},
        ],
        free_shipping_threshold=Decimal("200.00"),
    )
    card = PaymentMethod(
        name="Carte", provider_code="payzen", sort_order=1, fee=Decimal("2.00")
    )
    session.add_all([item, colissimo, card])
    await session.flush()
    return SimpleNamespace(
        user=cast(User, SimpleNamespace(id=user.id)),
        product=product,
        item=item,
        cart=cart,
        route=colissimo,
        card_id=card.id,
    )


@pytest.mark.asyncio
async def test_quote_adds_shipping_and_payment_fee(db_session: AsyncSession) -> None:
    seed = await _seed(db_session)

    quote = await get_checkout_quote(
        session=db_session,
        current_user=seed.user,
        address_id=None,
        delivery_type="home_delivery",
        payment_method_id=seed.card_id,
    )
    # 2 × 80 = 160 (< franco 200) ; 4 kg → band ≤ 10 kg = 12 ; card fee 2
    assert quote.subtotal_amount == Decimal("160.00")
    assert quote.shipping_fee_amount == Decimal("12.00")
    assert quote.payment_fee_amount == Decimal("2.00")
    assert quote.total_amount == Decimal("174.00")
    assert quote.free_shipping_applied is False
    assert quote.shipping_eta_days == 3
    assert quote.customs_declaration_fee == Decimal("0.00")


@pytest.mark.asyncio
async def test_quote_reflects_franco_and_no_payment_method(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    seed.item.quantity = 3  # 240 ≥ franco 200
    db_session.add(seed.item)
    await db_session.flush()

    quote = await get_checkout_quote(
        session=db_session,
        current_user=seed.user,
        address_id=None,
        delivery_type="home_delivery",
        payment_method_id=None,
    )
    assert quote.subtotal_amount == Decimal("240.00")
    assert quote.shipping_fee_amount == Decimal("0.00")
    assert quote.free_shipping_applied is True
    assert quote.payment_fee_amount == Decimal("0.00")
    assert quote.total_amount == Decimal("240.00")


@pytest.mark.asyncio
async def test_quote_refuses_an_unknown_delivery_mode(db_session: AsyncSession) -> None:
    seed = await _seed(db_session)
    with pytest.raises(AppError) as exc:
        await get_checkout_quote(
            session=db_session,
            current_user=seed.user,
            address_id=None,
            delivery_type="teleportation",
            payment_method_id=None,
        )
    assert exc.value.code == "checkout.delivery_type.unavailable"


@pytest.mark.asyncio
async def test_quote_without_cart_is_zero(db_session: AsyncSession) -> None:
    ghost = cast(User, SimpleNamespace(id=uuid.uuid4()))
    quote = await get_checkout_quote(
        session=db_session,
        current_user=ghost,
        address_id=None,
        delivery_type=None,
        payment_method_id=None,
    )
    assert quote.total_amount == Decimal("0.00")


@pytest.mark.asyncio
async def test_helper_is_the_single_source_for_checkout_amounts(
    db_session: AsyncSession,
) -> None:
    """The quote endpoint and the checkout call the same helper with the same
    inputs: assert the helper's amounts equal the endpoint's for one cart."""
    seed = await _seed(db_session)
    quote = await _quote_checkout(
        db_session,
        user_id=seed.user.id,
        currency=seed.cart.currency,
        items=[seed.item],
        products_by_id={seed.product.id: seed.product},
        shipping_address_id=None,
        delivery_type="home_delivery",
        payment_method_id=seed.card_id,
    )
    endpoint = await get_checkout_quote(
        session=db_session,
        current_user=seed.user,
        address_id=None,
        delivery_type="home_delivery",
        payment_method_id=seed.card_id,
    )
    assert (quote.subtotal_amount, quote.shipping_fee_amount, quote.total_amount) == (
        endpoint.subtotal_amount,
        endpoint.shipping_fee_amount,
        endpoint.total_amount,
    )
    assert quote.last_leg_route is not None and quote.last_leg_route.id == seed.route.id


@pytest.mark.asyncio
async def test_quote_stops_answering_about_codes_after_repeated_refusals(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit 2026-11, S7: the quote said « unknown / expired / exhausted »
    for any code, with no limit — an oracle to guess promo codes. Refusals
    are now counted per customer; past the limit the code is not looked up
    and the quote is priced without it."""
    from app.api.routes import cart as cart_routes

    monkeypatch.setattr(cart_routes, "QUOTE_COUPON_FAILURES_LIMIT", 3)
    seed = await _seed(db_session)

    async def quote(code: str) -> CheckoutQuoteResponse:
        return await get_checkout_quote(
            session=db_session,
            current_user=seed.user,
            address_id=None,
            delivery_type="home_delivery",
            payment_method_id=None,
            discount_code=code,
        )

    for attempt in range(3):
        refused = await quote(f"GUESS{attempt}")
        assert refused.discount_error
        assert refused.discount_error != cart_routes.QUOTE_COUPON_THROTTLED_MESSAGE

    throttled = await quote("GUESS-NEXT")
    assert throttled.discount_error == cart_routes.QUOTE_COUPON_THROTTLED_MESSAGE
    assert throttled.discount_amount == Decimal("0")
    assert throttled.subtotal_amount == Decimal("160.00")


@pytest.mark.asyncio
async def test_quote_without_code_is_never_throttled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.routes import cart as cart_routes

    monkeypatch.setattr(cart_routes, "QUOTE_COUPON_FAILURES_LIMIT", 1)
    seed = await _seed(db_session)
    for _ in range(5):
        quote = await get_checkout_quote(
            session=db_session,
            current_user=seed.user,
            address_id=None,
            delivery_type="home_delivery",
            payment_method_id=None,
        )
        assert quote.discount_error is None
