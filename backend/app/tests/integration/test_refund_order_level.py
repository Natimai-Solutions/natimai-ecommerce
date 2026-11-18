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


async def _order_in(
    session: AsyncSession, status_name: str, *, plan: str
) -> tuple[uuid.UUID, uuid.UUID]:
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    status = (
        await session.exec(
            select(OrderStatus).where(col(OrderStatus.name) == status_name)
        )
    ).first() or OrderStatus(name=status_name)
    session.add_all([user, status])
    await session.flush()
    order = Order(
        user_id=user.id,
        order_status_id=status.id,
        total_amount=Decimal("10000"),
        currency="XPF",
        payment_plan=plan,
        deposit_amount=Decimal("3000") if plan == "deposit" else Decimal("0"),
    )
    session.add(order)
    await session.flush()
    payment = Payment(
        order_id=order.id, user_id=user.id, amount=Decimal("10000"), currency="XPF"
    )
    session.add(payment)
    await session.flush()
    ids = (order.id, payment.id)
    await session.commit()
    return ids


async def _status_of(session: AsyncSession, order_id: uuid.UUID) -> str:
    session.expire_all()
    order = await session.get(Order, order_id)
    assert order is not None
    status = await session.get(OrderStatus, order.order_status_id)
    assert status is not None
    return status.name


@pytest.mark.asyncio
async def test_a_partial_refund_keeps_the_order_on_its_way(
    db_session: AsyncSession,
) -> None:
    """Review of 17/11/2026: a partial refund (one article missing) moved the
    order to « PartiallyRefunded » whatever its progress; it then followed
    its departure no more. The refund shows on the payment."""
    from app.handlers import payment as payment_handlers

    order_id, payment_id = await _order_in(db_session, "InTransit", plan="full")
    await payment_handlers.on_payment_refunded(
        db_session,
        {
            "order_id": str(order_id),
            "payment_id": str(payment_id),
            "amount": "2000",
            "fully_refunded": False,
        },
    )
    assert await _status_of(db_session, order_id) == "InTransit"

    # A full refund still ends it.
    await payment_handlers.on_payment_refunded(
        db_session,
        {
            "order_id": str(order_id),
            "payment_id": str(payment_id),
            "amount": "8000",
            "fully_refunded": True,
        },
    )
    assert await _status_of(db_session, order_id) == "Refunded"


@pytest.mark.asyncio
async def test_a_partially_refunded_deposit_order_still_stops_its_balance(
    db_session: AsyncSession,
) -> None:
    """Its balance does not deduct refunds: the status stays what keeps the
    full balance from being asked."""
    from app.handlers import payment as payment_handlers

    order_id, payment_id = await _order_in(db_session, "DepositPaid", plan="deposit")
    await payment_handlers.on_payment_refunded(
        db_session,
        {
            "order_id": str(order_id),
            "payment_id": str(payment_id),
            "amount": "1000",
            "fully_refunded": False,
        },
    )
    assert await _status_of(db_session, order_id) == "PartiallyRefunded"
