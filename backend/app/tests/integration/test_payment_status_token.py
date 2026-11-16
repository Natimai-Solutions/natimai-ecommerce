"""The return page reads a payment's status without a session, with the
signed token of the return URL (audit 2026-11: 3-D Secure finished in
another browser ended on « too long » for a successful payment)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.payments import get_payment_status_by_token
from app.core.errors import AppError
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.services.status_token import payment_status_token
from app.features.user.models.user import User


@pytest.mark.asyncio
async def test_the_signed_token_reads_one_status_and_nothing_else(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"p+{uuid.uuid4().hex[:6]}@t.local", hashed_password="x")
    completed = PaymentStatus(name="Completed")
    db_session.add_all([user, completed])
    await db_session.flush()
    payment = Payment(
        user_id=user.id,
        amount=Decimal("5000"),
        currency="XPF",
        provider_code="payzen",
        payment_status_id=completed.id,
    )
    db_session.add(payment)
    payment_id = payment.id
    await db_session.commit()

    status = await get_payment_status_by_token(
        payment_id, db_session, payment_status_token(payment_id)
    )
    assert status.status_name == "Completed" and status.is_terminal is True

    for wrong in ("0" * 32, payment_status_token(uuid.uuid4())):
        with pytest.raises(AppError) as refused:
            await get_payment_status_by_token(payment_id, db_session, wrong)
        assert refused.value.status_code == 404


@pytest.mark.asyncio
async def test_a_malformed_or_old_token_is_an_unknown_payment(
    db_session: AsyncSession,
) -> None:
    """A non-ASCII token raised (500: the payment exists); the link in the
    browser history read the status for ever."""
    from datetime import UTC, datetime, timedelta

    user = User(email=f"p+{uuid.uuid4().hex[:6]}@t.local", hashed_password="x")
    completed = PaymentStatus(name="Completed")
    db_session.add_all([user, completed])
    await db_session.flush()
    payment = Payment(
        user_id=user.id,
        amount=Decimal("5000"),
        currency="XPF",
        provider_code="payzen",
        payment_status_id=completed.id,
    )
    db_session.add(payment)
    payment_id = payment.id
    await db_session.commit()

    with pytest.raises(AppError) as refused:
        await get_payment_status_by_token(payment_id, db_session, "é" * 32)
    assert refused.value.status_code == 404

    payment.created_at = datetime.now(UTC) - timedelta(days=8)
    db_session.add(payment)
    await db_session.commit()
    with pytest.raises(AppError) as expired:
        await get_payment_status_by_token(
            payment_id, db_session, payment_status_token(payment_id)
        )
    assert expired.value.status_code == 404
