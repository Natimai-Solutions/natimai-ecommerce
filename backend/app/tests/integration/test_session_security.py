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


async def _refresh_with(
    session: AsyncSession, cookie: str, origin: str | None = None
) -> object:
    from fastapi import Response
    from starlette.requests import Request

    from app.api.routes.login import refresh_access_token
    from app.core.config import settings

    request = Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/login/refresh-token",
            "headers": [
                (b"cookie", f"{settings.REFRESH_COOKIE_NAME}={cookie}".encode()),
                *([(b"origin", origin.encode())] if origin else []),
            ],
            "client": ("203.0.113.7", 1234),
        }
    )
    return await refresh_access_token(request, Response(), session)


async def _active_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    from sqlmodel import col, select

    rows = await session.exec(
        select(UserRefreshToken).where(
            UserRefreshToken.user_id == user_id,
            col(UserRefreshToken.revoked_at).is_(None),
        )
    )
    return len(rows.all())


@pytest.mark.asyncio
async def test_a_new_stamp_also_closes_the_refresh_sessions(
    db_session: AsyncSession,
) -> None:
    """Audit 2026-11, S4: the refresh token carries the stamp too. A path that
    rotates the stamp without revoking the stored sessions (2FA reset…) no
    longer leaves a stolen refresh cookie alive for 30 days."""
    user_id, stamp = await _user(db_session)
    db_session.add(
        UserRefreshToken(
            user_id=user_id,
            jti="live",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()
    cookie = security.create_refresh_token(
        user_id, expires_delta=timedelta(days=1), jti="live", stamp=stamp
    )

    user = await db_session.get(User, user_id)
    assert user is not None
    user.security_stamp = security.new_security_stamp()
    await db_session.commit()

    with pytest.raises(AppError) as refused:
        await _refresh_with(db_session, cookie)
    assert refused.value.code == "login.refresh_token.revoked"
    assert await _active_sessions(db_session, user_id) == 0


@pytest.mark.asyncio
async def test_a_refresh_token_without_stamp_is_refused(
    db_session: AsyncSession,
) -> None:
    user_id, _ = await _user(db_session)
    db_session.add(
        UserRefreshToken(
            user_id=user_id,
            jti="legacy",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()
    cookie = security.create_refresh_token(
        user_id, expires_delta=timedelta(days=1), jti="legacy"
    )
    with pytest.raises(AppError) as refused:
        await _refresh_with(db_session, cookie)
    assert refused.value.code == "login.refresh_token.revoked"


@pytest.mark.asyncio
async def test_an_admin_session_is_refreshed_from_the_admin_origin_only(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit 2026-11, S2: a script injected in the storefront could exchange
    an administrator's refresh cookie (same API, CORS allowed) for an admin
    access token."""
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADMIN_FRONTEND_HOST", "https://admin.shop.test")
    admin = User(
        email=f"ops+{uuid.uuid4().hex[:8]}@test.local",
        hashed_password="x",
        is_superuser=True,
    )
    db_session.add(admin)
    admin_id, stamp = admin.id, admin.security_stamp
    await db_session.flush()
    db_session.add(
        UserRefreshToken(
            user_id=admin_id,
            jti="admin",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()
    cookie = security.create_refresh_token(
        admin_id, expires_delta=timedelta(days=1), jti="admin", stamp=stamp
    )

    with pytest.raises(AppError) as refused:
        await _refresh_with(db_session, cookie, origin="https://shop.test")
    assert refused.value.code == "login.refresh_token.admin_origin"
    # Nothing revoked: the administrator's own session goes on.
    assert await _active_sessions(db_session, admin_id) == 1
    assert await _refresh_with(db_session, cookie, origin="https://admin.shop.test/")


@pytest.mark.asyncio
async def test_a_customer_refreshes_from_the_storefront(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.core.config import settings

    monkeypatch.setattr(settings, "ADMIN_FRONTEND_HOST", "https://admin.shop.test")
    user_id, stamp = await _user(db_session)
    db_session.add(
        UserRefreshToken(
            user_id=user_id,
            jti="shop",
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await db_session.commit()
    cookie = security.create_refresh_token(
        user_id, expires_delta=timedelta(days=1), jti="shop", stamp=stamp
    )
    assert await _refresh_with(db_session, cookie, origin="https://shop.test")
