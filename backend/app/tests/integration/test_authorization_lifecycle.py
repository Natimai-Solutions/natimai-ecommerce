"""R8 / confort — a card authorisation's life after checkout: captured when the
order ships, released when it is cancelled, alerted before it expires."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_dashboard import build_dashboard
from app.core.config import settings
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.status import set_order_status
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.services import authorizations
from app.features.user.models.user import User
from app.handlers.payment import on_order_status_changed_capture_or_void
from app.outbox.models import OutboxEvent

_CAPTURE_UTIL = "app.features.payment.providers.payzen.capture_payzen_transaction"
_CANCEL_UTIL = "app.features.payment.providers.payzen.refund_payzen_transaction"


async def _seed(
    session: AsyncSession, *, created_at: datetime | None = None
) -> SimpleNamespace:
    customer = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    session.add(customer)
    await session.flush()
    authorized = PaymentStatus(name="Authorized")
    completed = PaymentStatus(name="Completed")
    paid = OrderStatus(name="Paid")
    session.add_all([authorized, completed, paid])
    await session.flush()
    order = Order(
        user_id=customer.id,
        order_status_id=paid.id,
        total_amount=Decimal("5000"),
        order_number=f"CMD-2026-{uuid.uuid4().int % 100000:05d}",
    )
    session.add(order)
    await session.flush()
    payment = Payment(
        user_id=customer.id,
        order_id=order.id,
        amount=Decimal("5000"),
        currency=settings.REFERENCE_CURRENCY,
        provider_code="payzen",
        payment_status_id=authorized.id,
        provider_data={"trans_uuid": "txn-auth-1"},
        created_at=created_at,
    )
    session.add(payment)
    await session.flush()
    ids = SimpleNamespace(
        order_id=order.id,
        payment_id=payment.id,
        authorized_id=authorized.id,
        completed_id=completed.id,
    )
    await session.commit()
    return ids


async def _payload(
    session: AsyncSession, order_id: uuid.UUID, status: str
) -> dict[str, Any]:
    order = await session.get(Order, order_id)
    assert order is not None
    await set_order_status(session, order=order, status_name=status, changed_by_id=None)
    await session.commit()
    event = (
        await session.exec(
            select(OutboxEvent)
            .where(col(OutboxEvent.type) == "order.status_changed")
            .order_by(col(OutboxEvent.created_at).desc())
        )
    ).first()
    assert event is not None
    return dict(event.payload)


@pytest.mark.asyncio
async def test_shipment_captures_the_authorised_payment(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    capture = AsyncMock(return_value={})
    monkeypatch.setattr(_CAPTURE_UTIL, capture)
    ids = await _seed(db_session)

    # Another step first: nothing happens.
    await on_order_status_changed_capture_or_void(
        db_session, await _payload(db_session, ids.order_id, "OrderedFromSupplier")
    )
    capture.assert_not_awaited()
    assert (await build_dashboard(db_session)).todo.payments_to_capture == 1

    await on_order_status_changed_capture_or_void(
        db_session, await _payload(db_session, ids.order_id, "InTransit")
    )
    capture.assert_awaited_once_with("txn-auth-1")
    db_session.expire_all()
    payment = await db_session.get(Payment, ids.payment_id)
    assert payment is not None and payment.payment_status_id == ids.completed_id
    captured = (
        await db_session.exec(
            select(OutboxEvent).where(col(OutboxEvent.type) == "payment.captured")
        )
    ).all()
    assert len(captured) == 1 and captured[0].payload["trigger"] == "auto"
    assert (await build_dashboard(db_session)).todo.payments_to_capture == 0


@pytest.mark.asyncio
async def test_cancellation_voids_the_authorisation(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    cancel = AsyncMock(
        return_value={"uuid": "txn-auth-1", "detailedStatus": "CANCELLED"}
    )
    monkeypatch.setattr(_CANCEL_UTIL, cancel)
    ids = await _seed(db_session)

    await on_order_status_changed_capture_or_void(
        db_session, await _payload(db_session, ids.order_id, "Cancelled")
    )
    cancel.assert_awaited_once()
    assert cancel.await_args is not None
    assert cancel.await_args.kwargs["amount_minor"] == 5000
    db_session.expire_all()
    payment = await db_session.get(Payment, ids.payment_id)
    assert payment is not None
    voided = (
        await db_session.exec(
            select(PaymentStatus).where(col(PaymentStatus.name) == "Voided")
        )
    ).one()
    assert payment.payment_status_id == voided.id
    assert payment.provider_data is not None and "voided_at" in payment.provider_data

    # A second cancellation finds nothing authorised: the provider is not called again.
    await authorizations.void_on_cancel(db_session, order_id=ids.order_id)
    cancel.assert_awaited_once()


@pytest.mark.asyncio
async def test_expiring_authorisations_are_alerted_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    alert = AsyncMock(return_value=True)
    monkeypatch.setattr(authorizations, "send_alert", alert)
    now = datetime(2026, 10, 3, 7, 0, tzinfo=UTC)
    old = await _seed(db_session, created_at=now - timedelta(days=6, hours=2))
    fresh = await _seed(db_session, created_at=now - timedelta(days=2))

    first = await authorizations.alert_expiring_authorizations(db_session, now=now)
    assert first == {"alerted": 1, "expiring": 1}
    alert.assert_awaited_once()
    assert alert.await_args is not None
    message = str(alert.await_args.args[0])
    assert str(old.payment_id) in message and str(fresh.payment_id) not in message

    again = await authorizations.alert_expiring_authorizations(db_session, now=now)
    assert again == {"alerted": 0, "expiring": 1}
    alert.assert_awaited_once()


async def _order_status(session: AsyncSession, order_id: uuid.UUID) -> str | None:
    session.expire_all()
    order = await session.get(Order, order_id)
    assert order is not None
    status = await session.get(OrderStatus, order.order_status_id)
    return status.name if status else None


@pytest.mark.asyncio
async def test_an_authorisation_secures_the_order_and_its_capture_keeps_it_moving(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit 2026-11, B3 + B6. The AUTHORISED notification published nothing:
    the order stayed « Pending », the sweep gave its stock away and it never
    reached the shipment that captures it. Then the capture at « InTransit »
    sent the order back to « Paid »."""
    from app.handlers.payment import on_payment_authorized, on_payment_captured

    monkeypatch.setattr(_CAPTURE_UTIL, AsyncMock(return_value={}))
    ids = await _seed(db_session)
    pending = OrderStatus(name="Pending")
    db_session.add(pending)
    await db_session.flush()
    order = await db_session.get(Order, ids.order_id)
    assert order is not None
    order.order_status_id = pending.id
    await db_session.commit()

    event = {"payment_id": str(ids.payment_id), "order_id": str(ids.order_id)}
    await on_payment_authorized(db_session, event)
    assert await _order_status(db_session, ids.order_id) == "Paid"

    # The departure ships: the authorisation is captured…
    await on_order_status_changed_capture_or_void(
        db_session, await _payload(db_session, ids.order_id, "InTransit")
    )
    # …and its payment.captured no longer moves the order back.
    await on_payment_captured(db_session, event)
    assert await _order_status(db_session, ids.order_id) == "InTransit"
