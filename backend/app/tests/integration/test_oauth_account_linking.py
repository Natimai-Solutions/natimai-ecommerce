"""Account linking rules of social sign-in, against a real database.

An e-mail a provider does not vouch for never creates nor takes over an
account, and an administrator account is never reachable through OAuth.
"""

from __future__ import annotations

import uuid

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.oauth import OAuthIdentity, OAuthRefused, _find_or_create_user
from app.features.user.models.oauth_link import UserOAuthLink
from app.features.user.models.user import User


def _identity(email: str, *, verified: bool, uid: str | None = None) -> OAuthIdentity:
    return OAuthIdentity(
        provider_user_id=uid or f"uid-{uuid.uuid4().hex[:8]}",
        email=email,
        full_name="Someone",
        email_verified=verified,
    )


async def _user(
    session: AsyncSession, email: str, *, superuser: bool = False, active: bool = True
) -> User:
    user = User(
        email=email,
        hashed_password="x",
        is_active=active,
        is_superuser=superuser,
        is_verified=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def _links(session: AsyncSession) -> list[UserOAuthLink]:
    return list((await session.exec(select(UserOAuthLink))).all())


@pytest.mark.asyncio
async def test_verified_email_links_the_existing_customer(
    db_session: AsyncSession,
) -> None:
    customer = await _user(db_session, "client@example.com")
    customer_id = customer.id

    user = await _find_or_create_user(
        db_session,
        provider="google",
        identity=_identity("client@example.com", verified=True, uid="g-1"),
    )
    user_id = user.id
    await db_session.commit()

    assert user_id == customer_id
    links = await _links(db_session)
    assert [(link.user_id, link.provider_user_id) for link in links] == [
        (customer_id, "g-1")
    ]


@pytest.mark.asyncio
async def test_unverified_email_never_takes_over_an_account(
    db_session: AsyncSession,
) -> None:
    await _user(db_session, "client@example.com")

    with pytest.raises(OAuthRefused) as refused:
        await _find_or_create_user(
            db_session,
            provider="microsoft",
            identity=_identity("client@example.com", verified=False),
        )
    assert refused.value.code == "email_not_verified"
    assert await _links(db_session) == []


@pytest.mark.asyncio
async def test_unverified_email_creates_no_account(db_session: AsyncSession) -> None:
    with pytest.raises(OAuthRefused) as refused:
        await _find_or_create_user(
            db_session,
            provider="microsoft",
            identity=_identity("new@example.com", verified=False),
        )
    assert refused.value.code == "email_not_verified"
    users = (await db_session.exec(select(User))).all()
    assert [u.email for u in users] == []


@pytest.mark.asyncio
async def test_verified_email_creates_a_customer_account(
    db_session: AsyncSession,
) -> None:
    user = await _find_or_create_user(
        db_session,
        provider="google",
        identity=_identity("new@example.com", verified=True),
    )
    await db_session.commit()
    await db_session.refresh(user)
    assert user.email == "new@example.com"
    assert user.is_superuser is False
    assert user.is_verified is True
    # A password nobody knows: the account opens through OAuth or a reset.
    assert user.hashed_password
    assert len(await _links(db_session)) == 1


@pytest.mark.asyncio
async def test_administrator_account_is_never_linked_by_email(
    db_session: AsyncSession,
) -> None:
    await _user(db_session, "admin@example.com", superuser=True)

    with pytest.raises(OAuthRefused) as refused:
        await _find_or_create_user(
            db_session,
            provider="google",
            identity=_identity("admin@example.com", verified=True),
        )
    assert refused.value.code == "account_exists"
    assert await _links(db_session) == []


@pytest.mark.asyncio
async def test_existing_link_to_an_administrator_is_refused(
    db_session: AsyncSession,
) -> None:
    # A link created before the fix (automatic linking by e-mail) must not
    # keep working.
    admin = await _user(db_session, "admin@example.com", superuser=True)
    db_session.add(
        UserOAuthLink(
            user_id=admin.id,
            provider="microsoft",
            provider_user_id="m-attacker",
            email_at_link="admin@example.com",
        )
    )
    await db_session.commit()

    with pytest.raises(OAuthRefused) as refused:
        await _find_or_create_user(
            db_session,
            provider="microsoft",
            identity=_identity("admin@example.com", verified=True, uid="m-attacker"),
        )
    assert refused.value.code == "superuser_oauth_disabled"


@pytest.mark.asyncio
async def test_existing_link_to_an_inactive_account_returns_it(
    db_session: AsyncSession,
) -> None:
    # Before, an inactive linked account fell through to the e-mail lookup;
    # now the linked account comes back and the callback refuses it.
    blocked = await _user(db_session, "blocked@example.com", active=False)
    blocked_id = blocked.id
    db_session.add(
        UserOAuthLink(
            user_id=blocked_id,
            provider="google",
            provider_user_id="g-blocked",
            email_at_link="blocked@example.com",
        )
    )
    await db_session.commit()

    user = await _find_or_create_user(
        db_session,
        provider="google",
        identity=_identity("other@example.com", verified=True, uid="g-blocked"),
    )
    assert user.id == blocked_id
    assert user.is_active is False
    assert len(await _links(db_session)) == 1
