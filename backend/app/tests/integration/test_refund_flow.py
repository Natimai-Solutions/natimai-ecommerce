"""Integration tests for the payment refund flow (real Postgres session)."""

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.refund import Refund
from app.features.payment.services.refund_service import refund_payment
from app.features.user.models.user import User
from app.outbox.models import OutboxEvent


async def _seed_payment(
    session: AsyncSession, *, amount: Decimal, provider_code: str = "manual_check"
) -> SimpleNamespace:
    customer = User(
        email=f"cust+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    session.add_all([customer, admin])
    await session.flush()

    payment = Payment(
        user_id=customer.id,
        amount=amount,
        currency="XPF",
        provider_code=provider_code,
    )
    # The refund service resolves these statuses by name.
    session.add_all(
        [
            payment,
            PaymentStatus(name="Refunded"),
            PaymentStatus(name="PartiallyRefunded"),
        ]
    )
    await session.flush()
    return SimpleNamespace(customer=customer, admin=admin, payment=payment)


async def _status_id(session: AsyncSession, name: str) -> uuid.UUID:
    result = await session.exec(
        select(PaymentStatus).where(col(PaymentStatus.name) == name)
    )
    status = result.first()
    assert status is not None
    return status.id


@pytest.mark.asyncio
async def test_refund_full_manual_sets_status_and_publishes(
    db_session: AsyncSession,
) -> None:
    seed = await _seed_payment(db_session, amount=Decimal("1000"))
    payment_id = seed.payment.id

    outcome = await refund_payment(
        session=db_session, payment=seed.payment, admin=seed.admin
    )

    assert outcome.refund.amount == Decimal("1000.00")
    assert outcome.refund.status == "completed"
    assert outcome.fully_refunded is True

    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    await db_session.refresh(payment)
    assert payment.payment_status_id == await _status_id(db_session, "Refunded")

    events = await db_session.exec(
        select(OutboxEvent).where(col(OutboxEvent.type) == "payment.refunded")
    )
    assert len(events.all()) == 1


@pytest.mark.asyncio
async def test_partial_then_remaining_refund(db_session: AsyncSession) -> None:
    seed = await _seed_payment(db_session, amount=Decimal("1000"))
    payment_id = seed.payment.id

    first = await refund_payment(
        session=db_session,
        payment=seed.payment,
        admin=seed.admin,
        amount=Decimal("400"),
    )
    assert first.fully_refunded is False
    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    await db_session.refresh(payment)
    assert payment.payment_status_id == await _status_id(
        db_session, "PartiallyRefunded"
    )

    # A real request gets a fresh admin; the previous refund commit expired this one.
    await db_session.refresh(seed.admin)
    # Refund the remaining 600 → fully refunded.
    second = await refund_payment(
        session=db_session, payment=payment, admin=seed.admin, amount=Decimal("600")
    )
    assert second.fully_refunded is True
    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    await db_session.refresh(payment)
    assert payment.payment_status_id == await _status_id(db_session, "Refunded")


@pytest.mark.asyncio
async def test_refund_exceeding_refundable_is_rejected(
    db_session: AsyncSession,
) -> None:
    seed = await _seed_payment(db_session, amount=Decimal("1000"))
    with pytest.raises(AppError) as exc:
        await refund_payment(
            session=db_session,
            payment=seed.payment,
            admin=seed.admin,
            amount=Decimal("1500"),
        )
    assert exc.value.status_code == 400


@pytest.mark.asyncio
async def test_payzen_refund_is_pending_without_status_change(
    db_session: AsyncSession,
) -> None:
    seed = await _seed_payment(
        db_session, amount=Decimal("1000"), provider_code="payzen"
    )
    payment_id = seed.payment.id

    outcome = await refund_payment(
        session=db_session, payment=seed.payment, admin=seed.admin
    )
    assert outcome.refund.status == "pending"
    assert outcome.fully_refunded is False

    # No payment status change and no event for a pending (manual back-office) refund.
    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    await db_session.refresh(payment)
    assert payment.payment_status_id is None

    events = await db_session.exec(
        select(OutboxEvent).where(col(OutboxEvent.type) == "payment.refunded")
    )
    assert len(events.all()) == 0

    # The refund is still recorded (reserves the amount).
    refunds = await db_session.exec(
        select(Refund).where(col(Refund.payment_id) == payment_id)
    )
    assert len(refunds.all()) == 1
