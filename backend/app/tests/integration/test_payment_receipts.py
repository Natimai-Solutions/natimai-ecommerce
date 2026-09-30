"""Instalments on manual payments (R3-P2), against a real database.

A customer pays at the office in several times; a cheque bounces; the deposit
of a deposit order is paid in cash and its balance by transfer, recorded at the
counter. The events the services publish are handed to their handlers like the
worker would, so the order statuses are the real ones.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_orders import get_order_detail
from app.api.routes.admin_payments import (
    PaymentApproveRequest,
    PaymentRejectRequest,
    approve_payment,
    reject_payment,
)
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_receipt import PaymentReceipt
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.services.receipts import (
    cancel_receipt,
    record_counter_payment,
    record_receipt,
)
from app.features.user.models.user import User
from app.handlers import order as order_handlers
from app.handlers import payment as payment_handlers
from app.outbox.models import OutboxEvent


@pytest.fixture(autouse=True)
def _quiet_side_effects(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stock, invoices and e-mails are covered elsewhere."""
    monkeypatch.setattr(
        payment_handlers, "confirm_order_stock", AsyncMock(return_value=0)
    )
    monkeypatch.setattr(payment_handlers, "issue_invoice_for_order", AsyncMock())
    monkeypatch.setattr(order_handlers, "_send_order_email", AsyncMock())


_HANDLERS = {
    "payment.captured": payment_handlers.on_payment_captured,
    "payment.partially_received": payment_handlers.on_payment_partially_received,
    "payment.receipt_cancelled": payment_handlers.on_payment_receipt_cancelled,
}


async def _drain(session: AsyncSession) -> list[str]:
    """Run the pending payment events through their handlers, like the worker."""
    events = (
        await session.exec(
            select(OutboxEvent)
            .where(col(OutboxEvent.status) == "PENDING")
            .order_by(col(OutboxEvent.created_at))
        )
    ).all()
    batch = [(event.type, dict(event.payload)) for event in events]
    for event in events:
        event.status = "DONE"
        session.add(event)
    await session.commit()
    handled = []
    for event_type, payload in batch:
        handler = _HANDLERS.get(event_type)
        if handler is not None:
            await handler(session, payload)
            handled.append(event_type)
    return handled


async def _seed(
    session: AsyncSession,
    *,
    total: str = "50000",
    plan: str = "full",
    deposit: str = "0",
    provider_code: str = "manual_cash",
    kind: str = "full",
    payment_amount: str | None = None,
) -> SimpleNamespace:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Teva Client",
        is_active=True,
        hashed_password="x",
    )
    statuses = {
        name: OrderStatus(name=name)
        for name in ("Pending", "AwaitingPayment", "Paid", "DepositPaid", "Received")
    }
    awaiting = PaymentStatus(name="AwaitingValidation")
    session.add_all([admin, buyer, awaiting, *statuses.values()])
    await session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=statuses["AwaitingPayment"].id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal(total),
        total_amount=Decimal(total),
        payment_plan=plan,
        deposit_amount=Decimal(deposit),
    )
    session.add(order)
    await session.flush()
    payment = Payment(
        order_id=order.id,
        user_id=buyer.id,
        amount=Decimal(payment_amount or (deposit if kind == "deposit" else total)),
        currency="XPF",
        provider_code=provider_code,
        kind=kind,
        payment_status_id=awaiting.id,
    )
    session.add(payment)
    await session.flush()
    seed = SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        order_id=order.id,
        payment_id=payment.id,
    )
    await session.commit()
    return seed


async def _order_status(session: AsyncSession, order_id: uuid.UUID) -> str | None:
    order = await session.get(Order, order_id)
    assert order is not None
    status = await session.get(OrderStatus, order.order_status_id)
    return status.name if status else None


async def _payment_status(session: AsyncSession, payment_id: uuid.UUID) -> str | None:
    payment = await session.get(Payment, payment_id)
    assert payment is not None
    status = await session.get(PaymentStatus, payment.payment_status_id)
    return status.name if status else None


async def _receipt(
    session: AsyncSession, seed: SimpleNamespace, amount: str, **extra: Any
) -> Any:
    payment = await session.get(Payment, seed.payment_id)
    assert payment is not None
    outcome = await record_receipt(
        session, payment=payment, admin=seed.admin, amount=Decimal(amount), **extra
    )
    snapshot = SimpleNamespace(
        receipt_id=outcome.receipt.id,
        received=outcome.received,
        remaining=outcome.remaining,
        settled=outcome.settled is not None,
    )
    await session.commit()
    return snapshot


@pytest.mark.asyncio
async def test_cash_in_instalments_pays_the_order_on_the_last_one(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    first = await _receipt(db_session, seed, "20000", reference="reçu 1")
    assert (first.received, first.remaining, first.settled) == (
        Decimal("20000"),
        Decimal("30000"),
        False,
    )
    assert await _drain(db_session) == ["payment.partially_received"]
    assert await _order_status(db_session, seed.order_id) == "PartiallyPaid"
    assert await _payment_status(db_session, seed.payment_id) == "AwaitingValidation"

    # More than what is left is refused, and changes nothing.
    with pytest.raises(AppError) as too_much:
        await _receipt(db_session, seed, "30001")
    assert too_much.value.code == "payment.receipt.exceeds_amount"
    await db_session.rollback()

    detail = await get_order_detail(seed.order_id, db_session, seed.admin)
    assert (detail.amount_paid, detail.amount_due) == (20000.0, 30000.0)
    assert (detail.next_part_kind, detail.next_part_due) == ("full", 30000.0)
    assert detail.payments[0].received_amount == 20000.0
    assert detail.payments[0].accepts_receipts is True

    last = await _receipt(db_session, seed, "30000")
    assert last.settled is True and last.remaining == 0
    assert await _drain(db_session) == ["payment.captured"]
    assert await _payment_status(db_session, seed.payment_id) == "Completed"
    assert await _order_status(db_session, seed.order_id) == "Paid"

    detail = await get_order_detail(seed.order_id, db_session, seed.admin)
    assert (detail.amount_paid, detail.amount_due) == (50000.0, 0.0)
    assert (detail.next_part_kind, detail.next_part_due) == (None, 0.0)
    assert [r.amount for r in detail.receipts] == [Decimal("20000"), Decimal("30000")]
    assert detail.payments[0].accepts_receipts is False

    # A settled payment takes no more receipt.
    with pytest.raises(AppError) as settled:
        await _receipt(db_session, seed, "1")
    assert settled.value.code == "payment.receipt.not_pending"


@pytest.mark.asyncio
async def test_a_bounced_cheque_is_cancelled_while_the_payment_is_pending(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session, provider_code="manual_check")
    cheque = await _receipt(db_session, seed, "20000", reference="CHQ 0012")
    await _drain(db_session)
    assert await _order_status(db_session, seed.order_id) == "PartiallyPaid"

    receipt = await db_session.get(PaymentReceipt, cheque.receipt_id)
    assert receipt is not None and receipt.method == "check"
    left = await cancel_receipt(
        db_session, receipt=receipt, admin=seed.admin, reason="Chèque impayé"
    )
    await db_session.commit()
    assert left == 0
    assert await _drain(db_session) == ["payment.receipt_cancelled"]
    assert await _order_status(db_session, seed.order_id) == "AwaitingPayment"

    receipt = await db_session.get(PaymentReceipt, cheque.receipt_id)
    assert receipt is not None
    assert receipt.is_active is False and receipt.cancel_reason == "Chèque impayé"
    with pytest.raises(AppError) as twice:
        await cancel_receipt(db_session, receipt=receipt, admin=seed.admin, reason="x")
    assert twice.value.code == "payment.receipt.already_cancelled"

    # Once the payment is settled, a receipt can no longer be cancelled here.
    settled = await _receipt(db_session, seed, "50000")
    assert settled.settled is True
    final = await db_session.get(PaymentReceipt, settled.receipt_id)
    assert final is not None
    with pytest.raises(AppError) as too_late:
        await cancel_receipt(db_session, receipt=final, admin=seed.admin, reason="x")
    assert too_late.value.code == "payment.receipt.payment_settled"


@pytest.mark.asyncio
async def test_deposit_in_cash_then_balance_by_transfer_at_the_counter(
    db_session: AsyncSession,
) -> None:
    # 100 000 XPF, 30 % deposit: 30 000 in cash (two instalments), then the
    # 70 000 balance received by transfer, recorded at the counter.
    seed = await _seed(
        db_session, total="100000", plan="deposit", deposit="30000", kind="deposit"
    )
    await _receipt(db_session, seed, "10000")
    await _drain(db_session)
    assert await _order_status(db_session, seed.order_id) == "PartiallyPaid"
    await _receipt(db_session, seed, "20000")
    await _drain(db_session)
    assert await _order_status(db_session, seed.order_id) == "DepositPaid"

    # The goods arrive; the customer pays the balance by transfer.
    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    received = (
        await db_session.exec(select(OrderStatus).where(OrderStatus.name == "Received"))
    ).one()
    order.order_status_id = received.id
    db_session.add(order)
    await db_session.commit()

    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    part = await record_counter_payment(
        db_session,
        order=order,
        admin=seed.admin,
        amount=Decimal("40000"),
        method="transfer",
        reference="VIR-2026-117",
    )
    balance_id = part.payment.id
    assert (part.payment.kind, part.payment.provider_code) == (
        "balance",
        "manual_transfer",
    )
    await db_session.commit()
    await _drain(db_session)
    # A receipt on the balance never pulls the order back from « Received ».
    assert await _order_status(db_session, seed.order_id) == "Received"

    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    rest = await record_counter_payment(
        db_session,
        order=order,
        admin=seed.admin,
        amount=Decimal("30000"),
        method="transfer",
    )
    # The same balance payment took the second receipt.
    assert rest.payment.id == balance_id and rest.settled is not None
    await db_session.commit()
    await _drain(db_session)
    order = await db_session.get(Order, seed.order_id)
    assert order is not None and order.balance_paid_at is not None

    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    with pytest.raises(AppError) as done:
        await record_counter_payment(
            db_session,
            order=order,
            admin=seed.admin,
            amount=Decimal("1"),
            method="cash",
        )
    assert done.value.code == "payment.order.already_paid"


@pytest.mark.asyncio
async def test_counter_cash_goes_on_the_transfer_the_customer_announced(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session, provider_code="manual_transfer")
    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    outcome = await record_counter_payment(
        db_session,
        order=order,
        admin=seed.admin,
        amount=Decimal("50000"),
        method="cash",
    )
    assert outcome.payment.id == seed.payment_id
    assert outcome.receipt.method == "cash"
    assert outcome.settled is not None
    await db_session.commit()
    payments = (
        await db_session.exec(
            select(Payment).where(col(Payment.order_id) == seed.order_id)
        )
    ).all()
    assert len(payments) == 1


@pytest.mark.asyncio
async def test_approve_settles_the_remainder_and_reject_waits_for_cancellations(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    await _receipt(db_session, seed, "15000")

    with pytest.raises(AppError) as refused:
        await reject_payment(
            seed.payment_id,
            PaymentRejectRequest(reason="client absent"),
            db_session,
            seed.admin,
        )
    assert refused.value.code == "payment.receipt.exists"

    response = await approve_payment(
        seed.payment_id,
        PaymentApproveRequest(reference="REÇU-88", comment="solde au comptoir"),
        db_session,
        seed.admin,
    )
    assert response.validation.action == "approve"
    assert await _payment_status(db_session, seed.payment_id) == "Completed"
    receipts = (
        await db_session.exec(
            select(PaymentReceipt)
            .where(col(PaymentReceipt.payment_id) == seed.payment_id)
            .order_by(col(PaymentReceipt.received_at))
        )
    ).all()
    assert [r.amount for r in receipts] == [Decimal("15000"), Decimal("35000")]
    assert receipts[-1].reference == "REÇU-88"

    # Approving twice no longer settles the payment twice.
    with pytest.raises(AppError) as again:
        await approve_payment(
            seed.payment_id, PaymentApproveRequest(), db_session, seed.admin
        )
    assert again.value.code == "payment.receipt.not_pending"


@pytest.mark.asyncio
async def test_receipts_are_only_for_manual_payments(db_session: AsyncSession) -> None:
    seed = await _seed(db_session, provider_code="payzen")
    with pytest.raises(AppError) as refused:
        await _receipt(db_session, seed, "100")
    assert refused.value.code == "payment.receipt.not_manual"
