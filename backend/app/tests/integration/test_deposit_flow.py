"""Integration tests (real DB): a deposit order from its first payment to its
balance — the initiation guard by payment kind, the capture / rejection /
invoice handlers, the balance request when the goods are received, and the
admin re-send."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_orders import request_order_balance
from app.api.routes.admin_price_groups import update_price_group
from app.api.routes.orders_me import list_my_orders
from app.api.routes.payments import _validate_order_for_initiation
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.product.models.price_group import PriceGroup, PriceGroupUpdate
from app.features.user.models.user import User
from app.handlers import order as order_handlers
from app.handlers import payment as payment_handlers

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


async def _seed(session: AsyncSession) -> SimpleNamespace:
    """A PRO group with a 30 % deposit, a buyer in it, and a deposit order of
    1 020 XPF (deposit 306, balance 714) with its pending deposit payment."""
    group = PriceGroup(
        code=f"PRO-{uuid.uuid4().hex[:6]}",
        label="Professionnel",
        deposit_pct=Decimal("30"),
        deposit_fee_pct=Decimal("2"),
    )
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    session.add_all([group, admin])
    await session.flush()
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Tehani Buyer",
        is_active=True,
        hashed_password="x",
        price_group_id=group.id,
    )
    statuses = {
        name: OrderStatus(name=name)
        for name in ("Pending", "Paid", "DepositPaid", "Received", "PaymentFailed")
    }
    completed, pending_ps = (
        PaymentStatus(name="Completed"),
        PaymentStatus(name="Pending"),
    )
    session.add_all([buyer, completed, pending_ps, *statuses.values()])
    await session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=statuses["Pending"].id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("1000"),
        total_fees_amount=Decimal("20"),
        total_amount=Decimal("1020"),
        payment_plan="deposit",
        deposit_amount=Decimal("306"),
        deposit_fee_amount=Decimal("20"),
    )
    session.add(order)
    await session.flush()
    deposit = Payment(
        order_id=order.id,
        user_id=buyer.id,
        amount=Decimal("306"),
        kind="deposit",
        payment_status_id=pending_ps.id,
    )
    session.add(deposit)
    await session.flush()
    # Read every id before the commit expires the instances.
    seed = SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        buyer=cast(User, SimpleNamespace(id=buyer.id, price_group_id=group.id)),
        group_id=group.id,
        order_id=order.id,
        deposit_payment_id=deposit.id,
        status_ids={name: s.id for name, s in statuses.items()},
        completed_id=completed.id,
    )
    await session.commit()
    return seed


async def _status_name(session: AsyncSession, order_id: uuid.UUID) -> str | None:
    order = await session.get(Order, order_id)
    assert order is not None
    status = await session.get(OrderStatus, order.order_status_id)
    return status.name if status else None


def _payload(
    seed: SimpleNamespace, payment_id: uuid.UUID, amount: str
) -> dict[str, Any]:
    return {
        "payment_id": str(payment_id),
        "order_id": str(seed.order_id),
        "user_id": str(seed.buyer.id),
        "total_amount": amount,
        "currency": "XPF",
        "provider_code": "payzen",
    }


@pytest.mark.asyncio
async def test_deposit_order_is_paid_in_two_guarded_payments(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(db_session)
    monkeypatch.setattr(
        payment_handlers, "confirm_order_stock", AsyncMock(return_value=0)
    )
    issue_invoice = AsyncMock()
    monkeypatch.setattr(payment_handlers, "issue_invoice_for_order", issue_invoice)

    async def guard(amount: str) -> str:
        return await _validate_order_for_initiation(
            db_session,
            order_id=seed.order_id,
            amount=Decimal(amount),
            currency="XPF",
            current_user=seed.buyer,
        )

    # 1. Nothing settled yet: the order accepts the deposit, at its amount only.
    assert await guard("306") == "deposit"
    with pytest.raises(AppError) as wrong:
        await guard("1020")
    assert wrong.value.code == "payment.amount.mismatch"
    assert wrong.value.details["expected_amount"] == "306"

    # 2. The deposit is captured: the order is « acompte versé », the stock is
    #    confirmed, no invoice yet (the capture e-mail is the receipt).
    deposit = await db_session.get(Payment, seed.deposit_payment_id)
    assert deposit is not None
    deposit.payment_status_id = seed.completed_id
    db_session.add(deposit)
    await db_session.commit()
    payload = _payload(seed, seed.deposit_payment_id, "306")
    await payment_handlers.on_payment_captured(db_session, payload)
    await payment_handlers.on_payment_captured_issue_invoice(db_session, payload)
    assert await _status_name(db_session, seed.order_id) == "DepositPaid"
    issue_invoice.assert_not_awaited()

    # 3. Now only the balance is accepted — and while the order is being
    #    fulfilled (Received), a status that refuses any first payment.
    assert await guard("714") == "balance"
    with pytest.raises(AppError):
        await guard("306")
    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    order.order_status_id = seed.status_ids["Received"]
    db_session.add(order)
    await db_session.commit()
    assert await guard("714") == "balance"

    # 4. A refused balance changes nothing on the order.
    balance = Payment(
        order_id=seed.order_id,
        user_id=seed.buyer.id,
        amount=Decimal("714"),
        kind="balance",
    )
    db_session.add(balance)
    await db_session.flush()
    balance_id = balance.id
    await db_session.commit()
    await payment_handlers.on_payment_rejected(
        db_session, _payload(seed, balance_id, "714")
    )
    assert await _status_name(db_session, seed.order_id) == "Received"

    # 5. The balance is captured: settled, invoiced, nothing more to pay.
    settled_balance = await db_session.get(Payment, balance_id)
    assert settled_balance is not None
    settled_balance.payment_status_id = seed.completed_id
    db_session.add(settled_balance)
    await db_session.commit()
    payload = _payload(seed, balance_id, "714")
    await payment_handlers.on_payment_captured(db_session, payload)
    order = await db_session.get(Order, seed.order_id)
    assert order is not None and order.balance_paid_at is not None
    assert await _status_name(db_session, seed.order_id) == "Received"
    issue_invoice.return_value = SimpleNamespace(
        id=uuid.uuid4(),
        invoice_number="FA-1",
        user_id=seed.buyer.id,
        currency="XPF",
        total_incl_tax=Decimal("1020"),
        total_tax=Decimal("0"),
    )
    await payment_handlers.on_payment_captured_issue_invoice(db_session, payload)
    issue_invoice.assert_awaited_once()
    with pytest.raises(AppError) as done:
        await guard("714")
    assert done.value.code == "payment.order.already_paid"


@pytest.mark.asyncio
async def test_balance_is_requested_once_at_reception_and_resendable_by_admin(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(db_session)
    send = AsyncMock(return_value=True)
    monkeypatch.setattr(order_handlers, "_send_order_email", send)
    payload = {
        "order_id": str(seed.order_id),
        "user_id": str(seed.buyer.id),
        "new_status": "Received",
    }

    await order_handlers.on_order_received_request_balance(db_session, payload)
    send.assert_awaited_once()
    kwargs = send.await_args.kwargs if send.await_args else {}
    assert "714" in kwargs["subject"]
    assert (
        "306" in kwargs["text"]
        and f"/mon-compte/commandes/{seed.order_id}/solde" in kwargs["text"]
    )
    order = await db_session.get(Order, seed.order_id)
    assert order is not None and order.balance_requested_at is not None

    # The customer sees the balance as due; a replay does not send it twice.
    mine = await list_my_orders(db_session, seed.buyer)
    assert mine[0].balance_due and mine[0].balance_amount == Decimal("714")
    await order_handlers.on_order_received_request_balance(db_session, payload)
    send.assert_awaited_once()

    # The admin can re-send it; not on a full-payment or settled order.
    result = await request_order_balance(seed.order_id, db_session, seed.admin)
    assert result.sent and result.balance_amount == 714.0
    assert send.await_count == 2
    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    order.balance_paid_at = NOW + timedelta(days=1)
    db_session.add(order)
    await db_session.commit()
    with pytest.raises(AppError) as settled:
        await request_order_balance(seed.order_id, db_session, seed.admin)
    assert settled.value.code == "order.balance.not_due"

    # A full-payment order is never asked for a balance.
    other = Order(
        user_id=seed.buyer.id,
        order_status_id=seed.status_ids["Received"],
        total_amount=Decimal("50"),
    )
    db_session.add(other)
    await db_session.flush()
    other_id = other.id
    await db_session.commit()
    await order_handlers.on_order_received_request_balance(
        db_session, {**payload, "order_id": str(other_id)}
    )
    assert send.await_count == 2


@pytest.mark.asyncio
async def test_admin_edits_the_deposit_policy_of_a_group(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    updated = await update_price_group(
        seed.group_id,
        PriceGroupUpdate(deposit_pct=Decimal("50"), deposit_required=True),
        db_session,
        seed.admin,
    )
    assert updated.deposit_pct == Decimal("50") and updated.deposit_required
    assert updated.deposit_fee_pct == Decimal("2")  # untouched
    with pytest.raises(AppError):
        await update_price_group(
            uuid.uuid4(), PriceGroupUpdate(deposit_pct=None), db_session, seed.admin
        )
