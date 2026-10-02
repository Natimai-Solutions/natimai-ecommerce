"""R8 / U9 — a visitor's server cart, its merge at sign-in, its reminder."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.cart import (
    GuestCartEmail,
    attach_guest_cart_email,
    clear_guest_cart,
    get_guest_cart,
    merge_guest_cart,
    replace_guest_cart_items,
    replace_my_cart_items,
)
from app.core.config import settings
from app.features.cart.models.cart import (
    Cart,
    CartItemAddRequest,
    CartReplaceRequest,
)
from app.features.cart.services.abandonment import (
    EVENT_CART_ABANDONED,
    open_carts_overview,
    remind_abandoned_carts,
)
from app.features.product.models.product import PricingMode, Product
from app.features.user.models.user import User
from app.outbox.models import OutboxEvent

TOKEN = "visitor-" + uuid.uuid4().hex


def _product(name: str, price: str = "1000") -> Product:
    return Product(name=name, pricing_mode=PricingMode.FIXED, base_price=Decimal(price))


async def _user(session: AsyncSession) -> User:
    user = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    return user


def _replace(*pairs: tuple[uuid.UUID, int]) -> CartReplaceRequest:
    return CartReplaceRequest(
        items=[CartItemAddRequest(product_id=pid, quantity=qty) for pid, qty in pairs]
    )


@pytest.mark.asyncio
async def test_guest_cart_lives_on_the_server_and_merges_at_sign_in(
    db_session: AsyncSession,
) -> None:
    cable, mouse, screen = _product("Câble"), _product("Souris"), _product("Écran")
    db_session.add_all([cable, mouse, screen])
    user = await _user(db_session)
    await db_session.flush()
    cable_id, mouse_id, screen_id = cable.id, mouse.id, screen.id
    await db_session.commit()
    await db_session.refresh(user)

    # Nothing yet: an empty detail, no row created.
    empty = await get_guest_cart(db_session, TOKEN)
    assert empty.items == [] and empty.user_id is None
    assert (await db_session.exec(select(Cart))).all() == []

    detail = await replace_guest_cart_items(
        db_session, TOKEN, _replace((cable_id, 2), (mouse_id, 1))
    )
    assert detail.user_id is None
    assert {(i.product_id, i.quantity) for i in detail.items} == {
        (cable_id, 2),
        (mouse_id, 1),
    }
    assert detail.total_amount == Decimal("3000")

    again = await get_guest_cart(db_session, TOKEN)
    assert again.id == detail.id

    await attach_guest_cart_email(
        db_session, TOKEN, GuestCartEmail(email="Visiteur@Example.PF")
    )
    guest_cart = (
        await db_session.exec(select(Cart).where(col(Cart.guest_token) == TOKEN))
    ).one()
    assert guest_cart.guest_email == "visiteur@example.pf"

    # The account already holds a cart from another device.
    await db_session.refresh(user)
    user_id = user.id
    await replace_my_cart_items(
        db_session, user, _replace((cable_id, 1), (screen_id, 1))
    )
    await db_session.refresh(user)

    merged = await merge_guest_cart(db_session, user, TOKEN)
    assert merged.user_id == user_id
    # Union of both carts; the larger quantity wins, never the sum.
    assert {(i.product_id, i.quantity) for i in merged.items} == {
        (cable_id, 2),
        (mouse_id, 1),
        (screen_id, 1),
    }
    # The guest cart is retired and its token forgotten by the server.
    assert (await get_guest_cart(db_session, TOKEN)).items == []
    db_session.expire_all()
    retired = (
        await db_session.exec(select(Cart).where(col(Cart.guest_token) == TOKEN))
    ).one()
    assert retired.is_active is False

    # Clearing an unknown token creates nothing.
    other = await clear_guest_cart(db_session, "unknown-" + uuid.uuid4().hex)
    assert other.items == []


@pytest.mark.asyncio
async def test_guest_carts_are_reminded_only_with_an_email(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(settings, "CART_ABANDONMENT_REMINDER_DELAY_HOURS", 24)
    monkeypatch.setattr(settings, "CART_ABANDONMENT_MAX_AGE_DAYS", 14)
    now = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)
    product = _product("Câble")
    db_session.add(product)
    await db_session.flush()
    product_id = product.id
    await db_session.commit()

    with_email = "with-" + uuid.uuid4().hex
    without_email = "without-" + uuid.uuid4().hex
    await replace_guest_cart_items(db_session, with_email, _replace((product_id, 1)))
    await attach_guest_cart_email(
        db_session, with_email, GuestCartEmail(email="hina@example.pf")
    )
    await replace_guest_cart_items(db_session, without_email, _replace((product_id, 1)))
    quiet = now - timedelta(hours=30)
    for cart in (await db_session.exec(select(Cart))).all():
        cart.last_activity_at = quiet
        db_session.add(cart)
    await db_session.commit()

    stats = await remind_abandoned_carts(db_session, now=now)
    assert stats["reminded"] == 1
    events = (
        await db_session.exec(
            select(OutboxEvent).where(col(OutboxEvent.type) == EVENT_CART_ABANDONED)
        )
    ).all()
    assert len(events) == 1
    payload = events[0].payload
    assert payload["user_id"] is None and payload["email"] == "hina@example.pf"

    page, counters = await open_carts_overview(db_session)
    assert counters["open"] == 2
    by_email = {row["user_email"]: row for row in page}
    assert by_email["hina@example.pf"]["guest"] is True
    assert None in by_email and by_email[None]["guest"] is True
