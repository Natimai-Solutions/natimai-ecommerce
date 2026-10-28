"""Integration (real DB): from « Mes commandes » the customer cancels an order
that received no money yet, and puts the articles of a past order back into
the cart."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import reorder_into_cart
from app.api.routes.orders_me import cancel_my_order, get_my_order
from app.api.routes.payments import payzen_ipn
from app.core.errors import AppError
from app.core.security import get_password_hash
from app.features.cart.models.cart import Cart, CartItem
from app.features.discount.models import Discount, DiscountTarget, DiscountType
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.product.models.product import PricingMode, Product
from app.features.user.models.user import User


async def _user(db_session: AsyncSession) -> User:
    user = User(
        email=f"client+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        is_verified=True,
        hashed_password=get_password_hash("mot-de-passe-client"),
    )
    db_session.add(user)
    await db_session.commit()
    await db_session.refresh(user)
    return user


async def _status(
    db_session: AsyncSession, model: type[OrderStatus] | type[PaymentStatus], name: str
) -> uuid.UUID:
    row: Any = (
        await db_session.exec(select(model).where(col(model.name) == name))
    ).first()
    if row is None:
        row = model(name=name)
        db_session.add(row)
        await db_session.flush()
    status_id: uuid.UUID = row.id
    return status_id


async def _order(
    db_session: AsyncSession,
    user: User,
    *,
    order_status: str,
    payment_status: str,
    discount_id: uuid.UUID | None = None,
) -> tuple[uuid.UUID, uuid.UUID]:
    await db_session.refresh(user)
    user_id = user.id
    order = Order(
        user_id=user_id,
        order_status_id=await _status(db_session, OrderStatus, order_status),
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("30000"),
        total_amount=Decimal("30000"),
        discount_id=discount_id,
    )
    db_session.add(order)
    await db_session.flush()
    payment = Payment(
        order_id=order.id,
        user_id=user_id,
        amount=Decimal("30000"),
        currency="XPF",
        provider_code="payzen",
        payment_status_id=await _status(db_session, PaymentStatus, payment_status),
    )
    db_session.add(payment)
    ids = (order.id, payment.id)
    await db_session.commit()
    return ids


@pytest.mark.asyncio
async def test_an_unpaid_order_is_cancelled_and_gives_its_coupon_back(
    db_session: AsyncSession,
) -> None:
    buyer = await _user(db_session)
    coupon = Discount(
        name="Bienvenue",
        discount_type=DiscountType.COUPON,
        target=DiscountTarget.ORDER,
        code="BIENVENUE",
        amount=Decimal("1000"),
        max_uses=10,
        current_uses=3,
    )
    db_session.add(coupon)
    await db_session.flush()
    coupon_id = coupon.id
    await db_session.commit()
    order_id, payment_id = await _order(
        db_session,
        buyer,
        order_status="Pending",
        payment_status="Pending",
        discount_id=coupon_id,
    )
    await db_session.refresh(buyer)

    before = await get_my_order(order_id, db_session, buyer)
    assert before.can_cancel is True

    after = await cancel_my_order(order_id, db_session, buyer)
    assert after.order_status_name == "Cancelled"
    assert after.can_cancel is False

    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    status = await db_session.get(PaymentStatus, payment.payment_status_id)
    assert status is not None and status.name == "Cancelled"
    refreshed = await db_session.get(Discount, coupon_id)
    assert refreshed is not None and refreshed.current_uses == 2

    # Twice is refused: the order is no longer in a cancellable state.
    await db_session.refresh(buyer)
    with pytest.raises(AppError) as again:
        await cancel_my_order(order_id, db_session, buyer)
    assert again.value.code == "order.cancel_refused"
    assert again.value.details["reason"] == "status"


@pytest.mark.asyncio
async def test_a_paid_order_or_someone_elses_is_not_cancelled(
    db_session: AsyncSession,
) -> None:
    buyer = await _user(db_session)
    stranger = await _user(db_session)
    # Status still « Pending » but the card is captured: money is in.
    order_id, _ = await _order(
        db_session, buyer, order_status="Pending", payment_status="Completed"
    )
    await db_session.refresh(buyer)
    await db_session.refresh(stranger)

    assert (await get_my_order(order_id, db_session, buyer)).can_cancel is False
    with pytest.raises(AppError) as paid:
        await cancel_my_order(order_id, db_session, buyer)
    assert paid.value.code == "order.cancel_refused"
    assert paid.value.details["reason"] == "paid"

    with pytest.raises(AppError) as foreign:
        await cancel_my_order(order_id, db_session, stranger)
    assert foreign.value.code == "order.not_found"
    assert foreign.value.status_code == 404


async def _status_name_of(db_session: AsyncSession, row: Order | Payment) -> str | None:
    status: OrderStatus | PaymentStatus | None
    if isinstance(row, Order):
        status = await db_session.get(OrderStatus, row.order_status_id)
    else:
        status = await db_session.get(PaymentStatus, row.payment_status_id)
    return status.name if status else None


@pytest.mark.asyncio
async def test_a_late_payzen_ipn_does_not_revive_a_cancelled_order(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The card form was still open in another tab: the customer cancels,
    then validates the card. PayZen's IPN finds the payment closed: it is
    kept on the payment for the shop to refund, the order stays cancelled
    and no capture is published (the stock is already back on sale)."""
    buyer = await _user(db_session)
    order_id, payment_id = await _order(
        db_session, buyer, order_status="Pending", payment_status="Pending"
    )
    await db_session.refresh(buyer)
    await cancel_my_order(order_id, db_session, buyer)

    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment_id),
                "trans_status": "PAID",
                "trans_uuid": "tx-late",
                "amount": "30000",
                "payment_cards": "VISA",
                "_raw_answer": {},
            }
        ),
    )
    captured = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_outcome_event", captured
    )
    request = cast(
        Request, SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "x"}))
    )
    response = await payzen_ipn(session=db_session, request=request)
    assert response.status_code == 200

    db_session.expire_all()
    payment = await db_session.get(Payment, payment_id)
    order = await db_session.get(Order, order_id)
    assert payment is not None and order is not None
    assert await _status_name_of(db_session, payment) == "Cancelled"
    assert await _status_name_of(db_session, order) == "Cancelled"
    captured.assert_not_awaited()
    # The shop can see the money came in after the cancellation.
    assert (payment.provider_data or {})["cancelled_conflict"]["trans_status"] == "PAID"


@pytest.mark.asyncio
async def test_money_that_comes_in_while_cancelling_keeps_the_order(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The refusal check reads the payments without a lock. Here it saw the
    payment still pending (patched), while the row — locked afterwards —
    is settled: the cancel is refused and nothing is written."""
    buyer = await _user(db_session)
    order_id, payment_id = await _order(
        db_session, buyer, order_status="Pending", payment_status="Completed"
    )
    await db_session.refresh(buyer)
    monkeypatch.setattr(
        "app.features.order.services.customer_actions.cancellation_refusal",
        AsyncMock(return_value=None),
    )

    with pytest.raises(AppError) as refused:
        await cancel_my_order(order_id, db_session, buyer)
    assert refused.value.code == "order.cancel_refused"
    assert refused.value.details["reason"] == "paid"

    await db_session.rollback()
    payment = await db_session.get(Payment, payment_id)
    order = await db_session.get(Order, order_id)
    assert payment is not None and order is not None
    assert await _status_name_of(db_session, payment) == "Completed"
    assert await _status_name_of(db_session, order) == "Pending"


@pytest.mark.asyncio
async def test_reorder_puts_the_articles_still_sold_back_into_the_cart(
    db_session: AsyncSession,
) -> None:
    buyer = await _user(db_session)
    stranger = await _user(db_session)
    sold = Product(
        name="Clavier",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("8000"),
        supplier_name="shop",
        supplier_sku=f"k-{uuid.uuid4().hex[:6]}",
    )
    gone = Product(
        name="Ancien modèle",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("5000"),
        is_active=False,
        supplier_name="shop",
        supplier_sku=f"g-{uuid.uuid4().hex[:6]}",
    )
    db_session.add_all([sold, gone])
    await db_session.flush()
    sold_id, gone_id = sold.id, gone.id
    order_id, _ = await _order(
        db_session, buyer, order_status="Delivered", payment_status="Completed"
    )
    db_session.add_all(
        [
            OrderLine(
                order_id=order_id,
                product_id=sold_id,
                quantity=2,
                unit_price=Decimal("8000"),
            ),
            OrderLine(
                order_id=order_id,
                product_id=gone_id,
                quantity=1,
                unit_price=Decimal("5000"),
            ),
        ]
    )
    # The cart already holds one keyboard: quantities add up.
    await db_session.refresh(buyer)
    cart = Cart(user_id=buyer.id, currency="XPF")
    db_session.add(cart)
    await db_session.flush()
    db_session.add(
        CartItem(
            cart_id=cart.id,
            product_id=sold_id,
            quantity=1,
            unit_price=Decimal("8000"),
        )
    )
    await db_session.commit()
    await db_session.refresh(buyer)
    await db_session.refresh(stranger)

    result = await reorder_into_cart(db_session, buyer, order_id)
    assert result.added == 1 and result.skipped == 1
    quantities = {item.product_id: item.quantity for item in result.cart.items}
    assert quantities == {sold_id: 3}

    await db_session.refresh(stranger)
    with pytest.raises(AppError) as foreign:
        await reorder_into_cart(db_session, stranger, order_id)
    assert foreign.value.code == "order.not_found"
