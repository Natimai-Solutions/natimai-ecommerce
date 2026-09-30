"""« Remboursée » is an order-level fact (R3-P2 follow-up).

An order settled by several payments — the deposit and the balance, or an
avoir next to cash — is fully refunded only when nothing it collected is
left. Refunding one of its payments used to flag the whole order as refunded
(order status « Refunded », stock given back).
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.services.refund_service import refund_payment
from app.features.user.models.user import User
from app.outbox.models import OutboxEvent


async def _seed(session: AsyncSession) -> SimpleNamespace:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    paid = OrderStatus(name="Paid")
    statuses = [
        PaymentStatus(name=name)
        for name in ("Completed", "Refunded", "PartiallyRefunded")
    ]
    session.add_all([admin, buyer, paid, *statuses])
    await session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=paid.id,
        currency="XPF",
        subtotal_amount=Decimal("100000"),
        total_amount=Decimal("100000"),
        payment_plan="deposit",
        deposit_amount=Decimal("30000"),
    )
    session.add(order)
    await session.flush()
    deposit = Payment(
        order_id=order.id,
        user_id=buyer.id,
        amount=Decimal("30000"),
        provider_code="manual_cash",
        kind="deposit",
        payment_status_id=statuses[0].id,
    )
    balance = Payment(
        order_id=order.id,
        user_id=buyer.id,
        amount=Decimal("70000"),
        provider_code="manual_transfer",
        kind="balance",
        payment_status_id=statuses[0].id,
    )
    session.add_all([deposit, balance])
    await session.flush()
    seed = SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        deposit_id=deposit.id,
        balance_id=balance.id,
    )
    await session.commit()
    return seed


async def _refund_events(session: AsyncSession) -> list[dict[str, Any]]:
    rows = await session.exec(
        select(OutboxEvent)
        .where(col(OutboxEvent.type) == "payment.refunded")
        .order_by(col(OutboxEvent.created_at))
    )
    return [dict(event.payload) for event in rows.all()]


@pytest.mark.asyncio
async def test_an_order_is_refunded_only_once_every_payment_is(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    balance = await db_session.get(Payment, seed.balance_id)
    assert balance is not None
    outcome = await refund_payment(db_session, payment=balance, admin=seed.admin)
    # The balance payment itself is fully refunded…
    assert outcome.fully_refunded is True
    events = await _refund_events(db_session)
    # …but the order still holds the deposit: not « remboursée ».
    assert events[-1]["payment_fully_refunded"] is True
    assert events[-1]["fully_refunded"] is False

    deposit = await db_session.get(Payment, seed.deposit_id)
    assert deposit is not None
    await refund_payment(
        db_session, payment=deposit, admin=seed.admin, amount=Decimal("10000")
    )
    events = await _refund_events(db_session)
    assert events[-1]["fully_refunded"] is False

    deposit = await db_session.get(Payment, seed.deposit_id)
    assert deposit is not None
    await refund_payment(db_session, payment=deposit, admin=seed.admin)
    events = await _refund_events(db_session)
    assert events[-1]["fully_refunded"] is True
    assert len(events) == 3
