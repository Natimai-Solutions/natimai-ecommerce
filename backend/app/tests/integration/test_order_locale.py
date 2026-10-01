"""The order's language drives its e-mails (R7 / L3)."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.user.models.user import User
from app.features.user.models.user_preference import UserPreference
from app.handlers.order import _email_lang


@pytest.mark.asyncio
async def test_email_language_order_then_preference_then_default(
    db_session: AsyncSession,
) -> None:
    user = User(email=f"u-{uuid.uuid4().hex[:6]}@example.com", hashed_password="x")
    status = OrderStatus(name=f"Pending-{uuid.uuid4().hex[:4]}")
    db_session.add_all([user, status])
    await db_session.flush()
    user_id, status_id = user.id, status.id
    order = Order(
        user_id=user_id,
        order_status_id=status_id,
        total_amount=Decimal("10"),
        subtotal_amount=Decimal("10"),
        locale="en",
    )
    db_session.add(order)
    await db_session.flush()
    order_id = order.id
    await db_session.commit()

    payload = {"order_id": str(order_id), "user_id": str(user_id)}
    assert await _email_lang(db_session, payload) == "en"

    # No order: the customer's saved preference, else the shop's default.
    assert await _email_lang(db_session, {"user_id": str(user_id)}) == "fr"
    db_session.add(UserPreference(user_id=user_id, locale="en"))
    await db_session.commit()
    assert await _email_lang(db_session, {"user_id": str(user_id)}) == "en"
