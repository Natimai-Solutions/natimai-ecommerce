"""Integration: the abandoned-cart sweep (real Postgres).

A quiet open cart is reminded once (one ``cart.abandoned`` outbox event, the
cart stamped); a fresh one, an ordered one, an empty one or an opted-out
customer's are not. The back-office overview counts them.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.cart.models.cart import Cart, CartItem
from app.features.cart.services.abandonment import (
    EVENT_CART_ABANDONED,
    open_carts_overview,
    remind_abandoned_carts,
)
from app.features.product.models.product import PricingMode, Product
from app.features.user.models.user import User
from app.features.user.models.user_preference import UserPreference
from app.outbox.models import OutboxEvent

NOW = datetime(2026, 9, 10, 12, 0, tzinfo=UTC)


async def _user(session: AsyncSession, *, marketing: bool | None = None) -> User:
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Client Test",
        is_active=True,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    if marketing is not None:
        session.add(UserPreference(user_id=user.id, marketing_email_enabled=marketing))
        await session.flush()
    return user


async def _cart(
    session: AsyncSession,
    user: User,
    product: Product | None,
    *,
    quiet_hours: float,
    checked_out: bool = False,
) -> Cart:
    stamp = NOW - timedelta(hours=quiet_hours)
    cart = Cart(
        user_id=user.id,
        currency="XPF",
        total_amount=Decimal("1500.00"),
        is_checked_out=checked_out,
        created_at=stamp,
        last_activity_at=stamp,
    )
    session.add(cart)
    await session.flush()
    if product is not None:
        session.add(
            CartItem(
                cart_id=cart.id,
                product_id=product.id,
                quantity=1,
                unit_price=Decimal("1500.00"),
                is_active=not checked_out,
            )
        )
        await session.flush()
    return cart


@pytest.mark.asyncio
async def test_quiet_open_carts_are_reminded_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CART_ABANDONMENT_REMINDER_DELAY_HOURS", 24)
    monkeypatch.setattr(settings, "CART_ABANDONMENT_MAX_AGE_DAYS", 14)
    product = Product(
        name="Câble", pricing_mode=PricingMode.FIXED, base_price=Decimal("1500")
    )
    db_session.add(product)
    await db_session.flush()

    quiet = await _cart(db_session, await _user(db_session), product, quiet_hours=30)
    fresh = await _cart(db_session, await _user(db_session), product, quiet_hours=2)
    ordered = await _cart(
        db_session, await _user(db_session), product, quiet_hours=30, checked_out=True
    )
    empty = await _cart(db_session, await _user(db_session), None, quiet_hours=30)
    ancient = await _cart(
        db_session, await _user(db_session), product, quiet_hours=24 * 20
    )
    opted_out = await _cart(
        db_session, await _user(db_session, marketing=False), product, quiet_hours=30
    )
    # Read before any commit: committed rows expire and cannot lazy-load.
    quiet_id = quiet.id
    await db_session.commit()

    stats = await remind_abandoned_carts(db_session, now=NOW)
    assert stats["reminded"] == 1
    assert stats["skipped_opt_out"] == 1

    events = (
        await db_session.exec(
            select(OutboxEvent).where(col(OutboxEvent.type) == EVENT_CART_ABANDONED)
        )
    ).all()
    assert [e.payload["cart_id"] for e in events] == [str(quiet_id)]
    assert events[0].payload["items"][0]["name"] == "Câble"

    for cart in (quiet, fresh, ordered, empty, ancient, opted_out):
        await db_session.refresh(cart)
    assert quiet.abandonment_reminded_at is not None
    assert opted_out.abandonment_reminded_at is not None  # stamped, never mailed
    assert all(
        c.abandonment_reminded_at is None for c in (fresh, ordered, empty, ancient)
    )

    # Next tick: nothing left to do.
    again = await remind_abandoned_carts(db_session, now=NOW + timedelta(hours=1))
    assert again["reminded"] == 0

    page, counters = await open_carts_overview(db_session)
    assert counters["open"] == 4  # quiet, fresh, ancient, opted_out (not ordered/empty)
    assert counters["reminded"] == 2
    assert counters["recovered"] == 0
    assert {row["cart_id"] for row in page} == {
        str(c.id) for c in (quiet, fresh, ancient, opted_out)
    }
