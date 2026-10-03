"""Integration (real DB): loyalty points (R8 / confort) — earned once when
an order is paid (gift cards excluded), taken back on a refund, converted
into store credit by the customer, adjusted by the admin."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.loyalty import adjust_loyalty, convert_points, my_loyalty
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.loyalty import LoyaltyAdjust, LoyaltyConvert
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.services import loyalty, store_credit
from app.features.product.models.product import PricingMode, Product
from app.features.system.settings_service import write_setting
from app.features.user.models.user import User
from app.handlers import payment as payment_handlers


async def _user(session: AsyncSession, *, superuser: bool = False) -> User:
    user = User(
        email=f"{'admin' if superuser else 'buyer'}+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=superuser,
        is_active=True,
        hashed_password="x",
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _fresh(session: AsyncSession, user: User) -> User:
    await session.refresh(user)
    return user


async def _enable(session: AsyncSession, admin_id: uuid.UUID) -> None:
    for key, raw in (
        ("loyalty_enabled", "true"),
        ("loyalty_amount_per_point", "100"),
        ("loyalty_point_value", "2"),
        ("loyalty_min_points_to_convert", "50"),
    ):
        await write_setting(session, key, raw, actor_id=admin_id)
    await session.commit()


async def _paid_order(
    session: AsyncSession, buyer_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID, dict[str, Any]]:
    statuses = {n: OrderStatus(name=n) for n in ("Pending", "Paid")}
    pstatuses = {n: PaymentStatus(name=n) for n in ("Pending", "Completed")}
    goods = Product(
        name="Écran",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("25000"),
        supplier_name="shop",
        supplier_sku=f"sc-{uuid.uuid4().hex[:6]}",
    )
    card = Product(
        name="Carte cadeau",
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("10000"),
        gift_card_amount=Decimal("10000"),
        supplier_name="shop",
        supplier_sku=f"gc-{uuid.uuid4().hex[:6]}",
    )
    session.add_all([*statuses.values(), *pstatuses.values(), goods, card])
    await session.flush()
    order = Order(
        user_id=buyer_id,
        order_status_id=statuses["Pending"].id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        total_amount=Decimal("61500"),
        shipping_fee_amount=Decimal("1500"),
    )
    session.add(order)
    await session.flush()
    payment = Payment(
        order_id=order.id,
        user_id=buyer_id,
        amount=Decimal("61500"),
        currency="XPF",
        provider_code="payzen",
        payment_status_id=pstatuses["Completed"].id,
    )
    session.add_all(
        [
            OrderLine(
                order_id=order.id,
                product_id=goods.id,
                quantity=2,
                unit_price=Decimal("25000"),
                discount_amount=Decimal("250"),
            ),
            OrderLine(
                order_id=order.id,
                product_id=card.id,
                quantity=1,
                unit_price=Decimal("10000"),
            ),
            payment,
        ]
    )
    order_id, payment_id = order.id, payment.id
    await session.commit()
    payload = {
        "payment_id": str(payment_id),
        "order_id": str(order_id),
        "user_id": str(buyer_id),
        "provider_code": "payzen",
        "total_amount": "61500",
        "currency": "XPF",
    }
    return order_id, payment_id, payload


@pytest.mark.asyncio
async def test_points_are_earned_once_on_the_goods_and_converted(
    db_session: AsyncSession,
) -> None:
    admin = await _user(db_session, superuser=True)
    admin_id = admin.id
    buyer = await _user(db_session)
    buyer_id = buyer.id
    await _enable(db_session, admin_id)
    order_id, _payment_id, payload = await _paid_order(db_session, buyer_id)

    await payment_handlers.on_payment_captured_issue_gift_cards(db_session, payload)
    # 2 × 25 000 − 250 = 49 750 of goods → 497 points; the gift card and the
    # shipping earn nothing.
    assert await loyalty.balance(db_session, buyer_id) == 497
    await payment_handlers.on_payment_captured_issue_gift_cards(db_session, payload)
    assert await loyalty.balance(db_session, buyer_id) == 497

    mine = await my_loyalty(db_session, await _fresh(db_session, buyer))
    assert mine.points == 497 and mine.credit_value == Decimal("994")
    assert mine.rules.enabled and mine.rules.min_points_to_convert == 50
    assert mine.entries[0].kind == "earn" and mine.entries[0].order_id == order_id

    with pytest.raises(AppError) as too_few:
        await convert_points(
            LoyaltyConvert(points=10), db_session, await _fresh(db_session, buyer)
        )
    assert too_few.value.code == "loyalty.below_minimum"
    with pytest.raises(AppError) as too_many:
        await convert_points(
            LoyaltyConvert(points=500), db_session, await _fresh(db_session, buyer)
        )
    assert too_many.value.code == "loyalty.insufficient"
    after = await convert_points(
        LoyaltyConvert(points=100), db_session, await _fresh(db_session, buyer)
    )
    assert after.points == 397
    assert after.entries[0].kind == "convert" and after.entries[0].points == -100
    assert await store_credit.balance(db_session, buyer_id) == Decimal("200")

    # A refund of a third takes back a third of the points earned.
    await payment_handlers.on_payment_refunded(
        db_session,
        {
            **payload,
            "amount": "20500",
            "fully_refunded": False,
            "payment_fully_refunded": False,
        },
    )
    assert await loyalty.balance(db_session, buyer_id) == 397 - 165

    with pytest.raises(AppError):
        await adjust_loyalty(
            buyer_id,
            LoyaltyAdjust(points=-1000, reason="Erreur"),
            db_session,
            await _fresh(db_session, admin),
        )
    bonus = await adjust_loyalty(
        buyer_id,
        LoyaltyAdjust(points=50, reason="Bienvenue"),
        db_session,
        await _fresh(db_session, admin),
    )
    assert bonus.points == 397 - 165 + 50 and bonus.entries[0].kind == "adjust"


@pytest.mark.asyncio
async def test_nothing_is_earned_while_the_programme_is_off(
    db_session: AsyncSession,
) -> None:
    buyer = await _user(db_session)
    buyer_id = buyer.id
    _order_id, _payment_id, payload = await _paid_order(db_session, buyer_id)
    await payment_handlers.on_payment_captured_issue_gift_cards(db_session, payload)
    assert await loyalty.balance(db_session, buyer_id) == 0
    mine = await my_loyalty(db_session, await _fresh(db_session, buyer))
    assert not mine.rules.enabled and mine.points == 0
    with pytest.raises(AppError) as off:
        await loyalty.convert(db_session, user_id=buyer_id, points=1)
    assert off.value.code == "loyalty.disabled"
