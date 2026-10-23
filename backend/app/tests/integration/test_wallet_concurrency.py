"""Integration (real DB, two sessions): money a customer holds cannot be
created or spent twice by concurrent requests — a gift card is redeemed
once, store credit and loyalty points are never spent past their balance."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.errors import AppError
from app.features.payment.models.gift_card import KIND_GIFT_CARD, GiftCard
from app.features.payment.services import gift_cards, loyalty, store_credit
from app.features.system.settings_service import write_setting
from app.features.user.models.user import User


async def _user(session: AsyncSession) -> uuid.UUID:
    user = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    session.add(user)
    user_id = user.id
    await session.commit()
    return user_id


async def _race(
    db_session: AsyncSession, attempt: Callable[[AsyncSession], Awaitable[Any]]
) -> list[Any]:
    """Run ``attempt`` in two sessions at once, each committing its work;
    returns what each one returned or raised."""
    engine = db_session.bind

    async def one() -> Any:
        async with AsyncSession(engine, expire_on_commit=False) as session:
            result = await attempt(session)
            await session.commit()
            return result

    return list(await asyncio.gather(one(), one(), return_exceptions=True))


def _meet_after(monkeypatch: pytest.MonkeyPatch, module: Any, name: str) -> None:
    """Make both racers wait for each other right after ``module.name``
    returns: without a lock, both have then read the same state before either
    writes. With the lock, the second one is blocked before the call; the
    first one stops waiting after a short delay and goes on alone."""
    original = getattr(module, name)
    barrier = asyncio.Barrier(2)

    async def wrapped(*args: Any, **kwargs: Any) -> Any:
        result = await original(*args, **kwargs)
        try:
            await asyncio.wait_for(barrier.wait(), timeout=0.5)
        except TimeoutError:
            pass
        return result

    monkeypatch.setattr(module, name, wrapped)


def _codes(outcomes: list[Any]) -> list[str]:
    return sorted(o.code if isinstance(o, AppError) else "ok" for o in outcomes)


@pytest.mark.asyncio
async def test_a_gift_card_redeemed_twice_at_once_credits_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = await _user(db_session)
    card = GiftCard(
        code=gift_cards.generate_code(),
        kind=KIND_GIFT_CARD,
        amount=Decimal("5000"),
        currency="XPF",
    )
    db_session.add(card)
    code = card.code
    await db_session.commit()

    async def redeem(session: AsyncSession) -> Any:
        user = await session.get(User, user_id)
        assert user is not None
        return await gift_cards.redeem(session, code=code, user=user)

    # The card has been read as active when the credit is granted.
    _meet_after(monkeypatch, store_credit, "grant")
    outcomes = await _race(db_session, redeem)

    assert _codes(outcomes) == ["gift_card.redeemed", "ok"]
    assert await store_credit.balance(db_session, user_id) == Decimal("5000")


@pytest.mark.asyncio
async def test_store_credit_spent_twice_at_once_never_goes_negative(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = await _user(db_session)
    await store_credit.grant(
        db_session,
        user_id=user_id,
        amount=Decimal("100"),
        reason="Geste commercial",
        currency="XPF",
        order_id=None,
        admin=None,
    )
    await db_session.commit()

    async def revoke(session: AsyncSession) -> Any:
        return await store_credit.grant(
            session,
            user_id=user_id,
            amount=Decimal("-80"),
            reason="Reprise",
            currency="XPF",
            order_id=None,
            admin=None,
        )

    _meet_after(monkeypatch, store_credit, "balance")
    outcomes = await _race(db_session, revoke)

    assert _codes(outcomes) == ["ok", "store_credit.insufficient"]
    assert await store_credit.balance(db_session, user_id) == Decimal("20")


@pytest.mark.asyncio
async def test_loyalty_points_converted_twice_at_once_convert_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = await _user(db_session)
    for key, raw in (
        ("loyalty_enabled", "true"),
        ("loyalty_point_value", "2"),
        ("loyalty_min_points_to_convert", "50"),
    ):
        await write_setting(db_session, key, raw, actor_id=None)
    await loyalty.adjust(
        db_session,
        user_id=user_id,
        points=100,
        reason="Bienvenue",
        order_id=None,
        admin=None,
    )
    await db_session.commit()

    async def convert(session: AsyncSession) -> Any:
        return await loyalty.convert(session, user_id=user_id, points=60)

    _meet_after(monkeypatch, loyalty, "balance")
    outcomes = await _race(db_session, convert)

    assert _codes(outcomes) == ["loyalty.insufficient", "ok"]
    assert await loyalty.balance(db_session, user_id) == 40
    assert await store_credit.balance(db_session, user_id) == Decimal("120")
