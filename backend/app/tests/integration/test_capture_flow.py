"""Integration tests for deferred CB capture (authorise at checkout, debit later)."""

import uuid
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.services.capture_service import capture_payment
from app.features.user.models.user import User
from app.outbox.models import OutboxEvent

# The PayZen REST capture call is mocked — these tests cover the service logic.
_CAPTURE_UTIL = "app.features.payment.providers.payzen.capture_payzen_transaction"


async def _seed_authorized_payment(
    session: AsyncSession, *, status_name: str = "Authorized"
) -> SimpleNamespace:
    customer = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    admin = User(
        email=f"a+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    session.add_all([customer, admin])
    await session.flush()

    authorized = PaymentStatus(name="Authorized")
    completed = PaymentStatus(name="Completed")
    session.add_all([authorized, completed])
    await session.flush()

    status = authorized if status_name == "Authorized" else completed
    payment = Payment(
        user_id=customer.id,
        amount=Decimal("5000"),
        currency="XPF",
        provider_code="payzen",
        payment_status_id=status.id,
        provider_data={"trans_uuid": "txn-123"},
    )
    session.add(payment)
    await session.flush()
    return SimpleNamespace(
        customer=customer,
        admin=admin,
        payment=payment,
        completed_id=completed.id,
    )


@pytest.mark.asyncio
async def test_capture_authorized_payment_marks_completed_and_publishes(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_CAPTURE_UTIL, AsyncMock(return_value={}))
    seed = await _seed_authorized_payment(db_session)
    payment_id = seed.payment.id

    outcome = await capture_payment(
        session=db_session, payment=seed.payment, admin=seed.admin
    )
    assert outcome.payment.payment_status_id == seed.completed_id

    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    await db_session.refresh(payment)
    assert payment.payment_status_id == seed.completed_id

    events = await db_session.exec(
        select(OutboxEvent).where(col(OutboxEvent.type) == "payment.captured")
    )
    assert len(events.all()) == 1


@pytest.mark.asyncio
async def test_capture_rejected_when_payment_not_authorized(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(_CAPTURE_UTIL, AsyncMock(return_value={}))
    seed = await _seed_authorized_payment(db_session, status_name="Completed")
    with pytest.raises(AppError) as exc:
        await capture_payment(
            session=db_session, payment=seed.payment, admin=seed.admin
        )
    assert exc.value.status_code == 400
