"""The PayZen IPN records its events in the shared provider journal
(``payment_webhook_events``), like every other provider."""

from __future__ import annotations

import json
import uuid
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock, Mock

import pytest
from fastapi import Request
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.orders_me import cancel_my_order
from app.api.routes.payments import payzen_ipn
from app.core.security import get_password_hash
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.payment_webhook_event import PaymentWebhookEvent
from app.features.user.models.user import User


async def _status(
    db_session: AsyncSession, model: type[OrderStatus] | type[PaymentStatus], name: str
) -> uuid.UUID:
    row: Any = (
        await db_session.exec(select(model).where(col(model.name) == name))
    ).first()
    if row is None:
        row = model(name=name)
        db_session.add(row)
        await db_session.flush()
    status_id: uuid.UUID = row.id
    return status_id


async def _pending_payment(
    db_session: AsyncSession,
) -> tuple[User, uuid.UUID, uuid.UUID]:
    user = User(
        email=f"client+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        is_verified=True,
        hashed_password=get_password_hash("mot-de-passe-client"),
    )
    db_session.add(user)
    await db_session.flush()
    order = Order(
        user_id=user.id,
        order_status_id=await _status(db_session, OrderStatus, "Pending"),
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("30000"),
        total_amount=Decimal("30000"),
    )
    db_session.add(order)
    await db_session.flush()
    payment = Payment(
        order_id=order.id,
        user_id=user.id,
        amount=Decimal("30000"),
        currency="XPF",
        provider_code="payzen",
        payment_status_id=await _status(db_session, PaymentStatus, "Pending"),
    )
    db_session.add(payment)
    ids = (order.id, payment.id)
    await db_session.commit()
    await db_session.refresh(user)
    return user, *ids


async def _send_ipn(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    payment_id: uuid.UUID,
    *,
    trans_status: str,
    trans_uuid: str = "tx-1",
    amount: str = "30000",
) -> dict[str, Any]:
    monkeypatch.setattr(
        "app.api.routes.payments.validate_ipn_signature",
        Mock(
            return_value={
                "order_id": str(payment_id),
                "trans_status": trans_status,
                "trans_uuid": trans_uuid,
                "amount": amount,
                "payment_cards": "VISA",
                "_raw_answer": {},
            }
        ),
    )
    request = cast(
        Request, SimpleNamespace(form=AsyncMock(return_value={"kr-answer": "x"}))
    )
    response = await payzen_ipn(session=db_session, request=request)
    assert response.status_code == 200
    body: dict[str, Any] = json.loads(bytes(response.body).decode("utf-8"))
    return body


async def _journal(
    db_session: AsyncSession, payment_id: uuid.UUID
) -> list[PaymentWebhookEvent]:
    db_session.expire_all()
    return list(
        (
            await db_session.exec(
                select(PaymentWebhookEvent)
                .where(col(PaymentWebhookEvent.payment_id) == payment_id)
                .order_by(col(PaymentWebhookEvent.received_at))
            )
        ).all()
    )


@pytest.mark.asyncio
async def test_a_paid_ipn_is_journaled_once_and_its_replay_is_acknowledged(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, payment_id = await _pending_payment(db_session)
    published = AsyncMock(return_value=None)
    monkeypatch.setattr(
        "app.api.routes.payments._publish_provider_outcome_event", published
    )

    first = await _send_ipn(db_session, monkeypatch, payment_id, trans_status="PAID")
    replay = await _send_ipn(db_session, monkeypatch, payment_id, trans_status="PAID")

    assert first == {"status": "ok"}
    assert replay["message"] == "IPN deja traite"
    published.assert_awaited_once()
    journal = await _journal(db_session, payment_id)
    assert [
        (e.provider_code, e.event_id, e.event_type, e.outcome) for e in journal
    ] == [("payzen", "tx-1:PAID", "PAID", "applied")]


@pytest.mark.asyncio
async def test_authorisation_then_capture_are_two_events(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, payment_id = await _pending_payment(db_session)

    await _send_ipn(db_session, monkeypatch, payment_id, trans_status="AUTHORISED")
    await _send_ipn(db_session, monkeypatch, payment_id, trans_status="PAID")

    journal = await _journal(db_session, payment_id)
    assert {(e.event_id, e.outcome) for e in journal} == {
        ("tx-1:AUTHORISED", "applied"),
        ("tx-1:PAID", "applied"),
    }


@pytest.mark.asyncio
async def test_an_amount_mismatch_is_journaled_as_such(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    _, _, payment_id = await _pending_payment(db_session)

    body = await _send_ipn(
        db_session, monkeypatch, payment_id, trans_status="PAID", amount="100"
    )

    assert body["status"] == "error"
    assert [e.outcome for e in await _journal(db_session, payment_id)] == [
        "amount_mismatch"
    ]


@pytest.mark.asyncio
async def test_an_ipn_on_a_cancelled_payment_is_journaled_as_a_conflict(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    buyer, order_id, payment_id = await _pending_payment(db_session)
    await cancel_my_order(order_id, db_session, buyer)

    await _send_ipn(db_session, monkeypatch, payment_id, trans_status="PAID")

    assert [e.outcome for e in await _journal(db_session, payment_id)] == ["conflict"]
