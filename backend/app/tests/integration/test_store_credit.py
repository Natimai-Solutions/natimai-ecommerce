"""Integration tests (real DB): store credit (« avoir-crédit ») — grants and
revocations by the admin, the customer's balance, spending it on an order
next to a card payment, and the guards that only settle a part once every
payment on it has landed."""

from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.payments import _validate_order_for_initiation
from app.api.routes.store_credit import (
    grant_store_credit,
    my_store_credit,
    user_store_credit,
)
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.store_credit import StoreCreditGrant
from app.features.payment.services import store_credit
from app.features.user.models.user import User
from app.handlers import payment as payment_handlers


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
    statuses = {n: OrderStatus(name=n) for n in ("Pending", "Paid", "PaymentReview")}
    pstatuses = {n: PaymentStatus(name=n) for n in ("Pending", "Completed", "Failed")}
    session.add_all([admin, buyer, *statuses.values(), *pstatuses.values()])
    await session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=statuses["Pending"].id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        total_amount=Decimal("1000"),
    )
    session.add(order)
    await session.flush()
    seed = SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        buyer=cast(User, SimpleNamespace(id=buyer.id, email=buyer.email)),
        order_id=order.id,
        order_number=order.order_number,
        status_ids={n: s.id for n, s in statuses.items()},
        pstatus_ids={n: s.id for n, s in pstatuses.items()},
    )
    await session.commit()
    return seed


async def _order_status(session: AsyncSession, order_id: uuid.UUID) -> str | None:
    order = await session.get(Order, order_id)
    assert order is not None
    status = await session.get(OrderStatus, order.order_status_id)
    return status.name if status else None


@pytest.mark.asyncio
async def test_admin_grants_and_revokes_credit_the_customer_can_see(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    granted = await grant_store_credit(
        seed.buyer.id,
        StoreCreditGrant(
            amount=Decimal("300"), reason="Geste commercial", order_id=seed.order_id
        ),
        db_session,
        seed.admin,
    )
    assert granted.balance == Decimal("300") and granted.entries[0].kind == "grant"
    assert granted.entries[0].created_by_id == seed.admin.id

    # A revocation cannot dig below zero; a valid one is a signed entry.
    with pytest.raises(AppError) as too_much:
        await grant_store_credit(
            seed.buyer.id,
            StoreCreditGrant(amount=Decimal("-500"), reason="Erreur"),
            db_session,
            seed.admin,
        )
    assert too_much.value.code == "store_credit.insufficient"
    after = await grant_store_credit(
        seed.buyer.id,
        StoreCreditGrant(amount=Decimal("-100"), reason="Correction"),
        db_session,
        seed.admin,
    )
    assert after.balance == Decimal("200")
    assert {e.kind for e in after.entries} == {"grant", "revoke"}

    mine = await my_store_credit(db_session, seed.buyer)
    assert mine.balance == Decimal("200") and len(mine.entries) == 2
    assert (
        await user_store_credit(seed.buyer.id, db_session, seed.admin)
    ).balance == Decimal("200")
    with pytest.raises(AppError):
        await grant_store_credit(
            uuid.uuid4(),
            StoreCreditGrant(amount=Decimal("1"), reason="x"),
            db_session,
            seed.admin,
        )


@pytest.mark.asyncio
async def test_credit_settles_its_share_and_the_card_settles_the_rest(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(db_session)
    monkeypatch.setattr(
        payment_handlers, "confirm_order_stock", AsyncMock(return_value=0)
    )
    notify = AsyncMock()
    monkeypatch.setattr(payment_handlers, "send_payment_event_notifications", notify)
    await store_credit.grant(
        db_session,
        user_id=seed.buyer.id,
        amount=Decimal("300"),
        reason="Avoir",
        currency="XPF",
        order_id=None,
        admin=seed.admin,
    )
    await db_session.commit()

    # 300 of credit on a 1 000 order: a settled store_credit payment, the
    # ledger debited, and the balance gone.
    order = await db_session.get(Order, seed.order_id)
    assert order is not None
    with pytest.raises(AppError) as over:
        await store_credit.apply_to_order(
            db_session, order=order, user=seed.buyer, amount=Decimal("301"), kind="full"
        )
    assert over.value.code == "store_credit.insufficient"
    credit_payment = await store_credit.apply_to_order(
        db_session, order=order, user=seed.buyer, amount=Decimal("300"), kind="full"
    )
    credit_payment_id = credit_payment.id
    await db_session.commit()
    assert await store_credit.balance(db_session, seed.buyer.id) == Decimal("0")

    # The guard now expects the rest (700) from the card, not the total.
    assert (
        await _validate_order_for_initiation(
            db_session,
            order_id=seed.order_id,
            amount=Decimal("700"),
            currency="XPF",
            current_user=seed.buyer,
        )
        == "full"
    )
    with pytest.raises(AppError) as wrong:
        await _validate_order_for_initiation(
            db_session,
            order_id=seed.order_id,
            amount=Decimal("1000"),
            currency="XPF",
            current_user=seed.buyer,
        )
    assert wrong.value.details["expected_amount"] == "700"

    # The card payment is pending: the credit capture waits, the order stays
    # Pending and nobody is alerted.
    card = Payment(
        order_id=seed.order_id,
        user_id=seed.buyer.id,
        amount=Decimal("700"),
        kind="full",
        payment_status_id=seed.pstatus_ids["Pending"],
    )
    db_session.add(card)
    await db_session.flush()
    card_id = card.id
    await db_session.commit()

    def payload(payment_id: uuid.UUID) -> dict[str, str]:
        return {
            "payment_id": str(payment_id),
            "order_id": str(seed.order_id),
            "user_id": str(seed.buyer.id),
            "provider_code": "store_credit",
        }

    await payment_handlers.on_payment_captured(db_session, payload(credit_payment_id))
    assert await _order_status(db_session, seed.order_id) == "Pending"
    notify.assert_not_awaited()

    # The card lands: the part is exactly covered, the order is Paid.
    landed = await db_session.get(Payment, card_id)
    assert landed is not None
    landed.payment_status_id = seed.pstatus_ids["Completed"]
    db_session.add(landed)
    await db_session.commit()
    await payment_handlers.on_payment_captured(db_session, payload(card_id))
    assert await _order_status(db_session, seed.order_id) == "Paid"

    # Nothing more is accepted on the order.
    with pytest.raises(AppError) as done:
        await _validate_order_for_initiation(
            db_session,
            order_id=seed.order_id,
            amount=Decimal("1"),
            currency="XPF",
            current_user=seed.buyer,
        )
    assert done.value.code in {
        "payment.order.already_paid",
        "payment.order.not_payable",
    }


@pytest.mark.asyncio
async def test_a_short_capture_with_nothing_pending_is_still_parked(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(db_session)
    notify = AsyncMock()
    monkeypatch.setattr(payment_handlers, "send_payment_event_notifications", notify)
    short = Payment(
        order_id=seed.order_id,
        user_id=seed.buyer.id,
        amount=Decimal("1"),
        kind="full",
        payment_status_id=seed.pstatus_ids["Completed"],
    )
    db_session.add(short)
    await db_session.flush()
    short_id = short.id
    await db_session.commit()
    await payment_handlers.on_payment_captured(
        db_session,
        {
            "payment_id": str(short_id),
            "order_id": str(seed.order_id),
            "provider_code": "payzen",
        },
    )
    assert await _order_status(db_session, seed.order_id) == "PaymentReview"
    notify.assert_awaited_once()
