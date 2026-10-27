"""Integration (real DB): sessions close when they must — the access token
carries the user's ``security_stamp``, and a refresh token is rotated once
even by two concurrent refreshes."""

from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import get_current_user
from app.core import security
from app.core.errors import AppError
from app.features.user.crud.refresh_token import crud_user_refresh_token
from app.features.user.models.refresh_token import UserRefreshToken
from app.features.user.models.user import User


async def _user(session: AsyncSession) -> tuple[uuid.UUID, str]:
    user = User(email=f"buyer+{uuid.uuid4().hex[:8]}@test.local", hashed_password="x")
    session.add(user)
    user_id, stamp = user.id, user.security_stamp
    await session.commit()
    return user_id, stamp


@pytest.mark.asyncio
async def test_a_new_stamp_closes_the_open_access_tokens(
    db_session: AsyncSession,
) -> None:
    user_id, stamp = await _user(db_session)
    token = security.create_access_token(
        user_id, expires_delta=timedelta(minutes=15), stamp=stamp
    )
    assert (await get_current_user(db_session, token)).id == user_id

    # Password changed, account deactivated, 2FA reset… elsewhere.
    user = await db_session.get(User, user_id)
    assert user is not None
    user.security_stamp = security.new_security_stamp()
    await db_session.commit()

    with pytest.raises(AppError) as refused:
        await get_current_user(db_session, token)
    assert refused.value.status_code == 401
    assert refused.value.details["reason"] == "session_revoked"

    # Neither a token without stamp nor a refresh token passes for access.
    for other in (
        security.create_access_token(user_id, expires_delta=timedelta(minutes=15)),
        security.create_refresh_token(user_id, expires_delta=timedelta(days=1)),
    ):
        with pytest.raises(AppError):
            await get_current_user(db_session, other)


@pytest.mark.asyncio
async def test_two_concurrent_refreshes_rotate_the_token_once(
    db_session: AsyncSession,
) -> None:
    user_id, _ = await _user(db_session)
    token = UserRefreshToken(
        user_id=user_id,
        jti="old",
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    db_session.add(token)
    token_id = token.id
    await db_session.commit()

    async def refresh(new_jti: str) -> UserRefreshToken | None:
        async with AsyncSession(db_session.bind, expire_on_commit=False) as session:
            current = await session.get(UserRefreshToken, token_id)
            assert current is not None
            return await crud_user_refresh_token.rotate_token(
                session,
                current_token=current,
                new_jti=new_jti,
                new_expires_at=datetime.now(UTC) + timedelta(days=1),
            )

    outcomes = await asyncio.gather(refresh("a"), refresh("b"))

    # One live successor; the other refresh is a reuse (None → family revoked).
    assert sorted(o is None for o in outcomes) == [False, True]
