"""Integration tests (real DB): a quote request made without an account is
reached by e-mail only from an account whose address is proven.

A guest session (``POST /signup/guest``) is opened for any address without
an account and proves nothing: it must not read, download or order the
quote of a visitor who used the same address (chantier accueil et
messagerie, §12.2)."""

from __future__ import annotations

import uuid

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import cart as cart_routes
from app.core.errors import AppError
from app.features.cart.models.quote_request import QuoteRequest, QuoteRequestStatus
from app.features.cart.services.quote import check_convertible
from app.features.user.models.user import User

pytestmark = pytest.mark.asyncio


async def _visitor_quote(session: AsyncSession, email: str) -> QuoteRequest:
    quote = QuoteRequest(
        user_id=None,
        email=email,
        full_name="Visiteur Tama",
        phone="+689 87 00 00 00",
        shipping_address="BP 42, Papeete",
        status=QuoteRequestStatus.REQUESTED.value,
        items_snapshot={"currency": "XPF", "items": []},
    )
    session.add(quote)
    await session.flush()
    return quote


async def _account(
    session: AsyncSession, email: str, *, verified: bool, guest: bool
) -> User:
    user = User(
        email=email,
        is_active=True,
        is_verified=verified,
        is_guest=guest,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    return user


@pytest.mark.parametrize(
    ("verified", "guest"),
    [(False, True), (False, False)],
    ids=["guest-session", "unverified-account"],
)
async def test_an_unproven_address_does_not_reach_a_visitor_quote(
    db_session: AsyncSession, verified: bool, guest: bool
) -> None:
    email = f"visitor+{uuid.uuid4().hex[:8]}@test.local"
    quote = await _visitor_quote(db_session, email)
    intruder = await _account(db_session, email, verified=verified, guest=guest)

    assert await cart_routes.list_my_quotes(db_session, intruder) == []
    with pytest.raises(AppError) as read:
        await cart_routes._my_quote_or_404(db_session, quote.id, intruder)
    assert read.value.status_code == 404
    with pytest.raises(AppError) as order:
        check_convertible(quote, user=intruder)
    assert order.value.status_code == 404


async def test_a_proven_address_finds_the_quote_it_made_before_signing_up(
    db_session: AsyncSession,
) -> None:
    email = f"visitor+{uuid.uuid4().hex[:8]}@test.local"
    quote = await _visitor_quote(db_session, email)
    owner = await _account(db_session, email.upper(), verified=True, guest=False)

    listed = await cart_routes.list_my_quotes(db_session, owner)
    assert [item.id for item in listed] == [quote.id]
    assert (await cart_routes._my_quote_or_404(db_session, quote.id, owner)).id == (
        quote.id
    )


async def test_a_quote_of_another_account_never_matches_by_email(
    db_session: AsyncSession,
) -> None:
    email = f"buyer+{uuid.uuid4().hex[:8]}@test.local"
    first = await _account(db_session, email, verified=True, guest=False)
    quote = await _visitor_quote(db_session, email)
    quote.user_id = first.id
    db_session.add(quote)
    other = await _account(
        db_session,
        f"other+{uuid.uuid4().hex[:8]}@test.local",
        verified=True,
        guest=False,
    )
    await db_session.flush()

    assert await cart_routes.list_my_quotes(db_session, other) == []
    with pytest.raises(AppError):
        await cart_routes._my_quote_or_404(db_session, quote.id, other)
