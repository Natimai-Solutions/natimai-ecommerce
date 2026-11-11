"""Two-factor authentication of the administrators (R6)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from cryptography.fernet import Fernet
from fastapi import Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession
from starlette.requests import Request

from app.api import deps
from app.api.routes import login as login_routes
from app.api.routes import two_factor as routes
from app.api.routes.admin_users import reset_two_factor
from app.core import totp
from app.core.config import settings
from app.core.errors import AppError
from app.core.security import get_password_hash
from app.features.user.models.refresh_token import UserRefreshToken
from app.features.user.models.user import User
from app.features.user.services import two_factor

PASSWORD = "admin-password-for-tests"


@pytest.fixture(autouse=True)
def _env(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    monkeypatch.setattr(
        settings, "SECRETS_ENCRYPTION_KEY", Fernet.generate_key().decode()
    )
    monkeypatch.setattr(login_routes, "hit_rate_limit", AsyncMock(return_value=False))
    events: list[dict[str, Any]] = []

    async def capture(**kwargs: Any) -> None:
        events.append(kwargs)

    monkeypatch.setattr("app.features.system.audit.record", capture)
    return events


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/v1/login/access-token",
            "headers": [(b"user-agent", b"pytest")],
            "client": ("203.0.113.7", 1234),
        }
    )


async def _admin(session: AsyncSession, email: str = "ops@test.local") -> uuid.UUID:
    user = User(
        email=email,
        hashed_password=get_password_hash(PASSWORD),
        is_active=True,
        is_superuser=True,
    )
    session.add(user)
    user_id = user.id
    await session.commit()
    return user_id


async def _login(session: AsyncSession, email: str, code: str | None = None) -> Any:
    return await login_routes.login_access_token(
        _request(),
        Response(),
        session,
        OAuth2PasswordRequestForm(username=email, password=PASSWORD),
        totp_code=code,
    )


async def _enrol(session: AsyncSession, user_id: uuid.UUID) -> tuple[str, list[str]]:
    user = await session.get(User, user_id)
    assert user is not None
    setup = await routes.setup(session, user)
    assert setup.qr_svg_data_uri.startswith("data:image/svg+xml;base64,")
    user = await session.get(User, user_id)
    assert user is not None
    code = totp.code_at(setup.secret, totp.current_step() - 1)
    codes = await routes.confirm(
        _request(), routes.TwoFactorCode(code=code), session, user
    )
    return setup.secret, codes.recovery_codes


async def _open_session(session: AsyncSession, user_id: uuid.UUID) -> None:
    session.add(
        UserRefreshToken(
            user_id=user_id,
            jti=uuid.uuid4().hex,
            expires_at=datetime.now(UTC) + timedelta(days=1),
        )
    )
    await session.commit()


async def _active_sessions(session: AsyncSession, user_id: uuid.UUID) -> int:
    rows = await session.exec(
        select(UserRefreshToken).where(
            UserRefreshToken.user_id == user_id,
            col(UserRefreshToken.revoked_at).is_(None),
        )
    )
    return len(rows.all())


@pytest.mark.asyncio
async def test_enrolment_then_sign_in_needs_the_second_factor(
    db_session: AsyncSession, _env: list[dict[str, Any]]
) -> None:
    user_id = await _admin(db_session)
    # Before enrolment: password alone.
    assert (await _login(db_session, "ops@test.local")).access_token

    secret, recovery = await _enrol(db_session, user_id)
    assert len(recovery) == two_factor.RECOVERY_CODE_COUNT
    user = await db_session.get(User, user_id)
    assert user is not None and user.totp_enabled is True
    assert secret not in (user.totp_secret_encrypted or "")
    assert recovery[0] not in str(user.totp_recovery_hashes)

    with pytest.raises(AppError) as missing:
        await _login(db_session, "ops@test.local")
    assert missing.value.code == "login.totp.required"

    with pytest.raises(AppError) as wrong:
        await _login(db_session, "ops@test.local", "000000")
    assert wrong.value.code == "login.totp.invalid"
    user = await db_session.get(User, user_id)
    assert user is not None and user.failed_login_attempts == 1

    current = totp.code_at(secret, totp.current_step())
    assert (await _login(db_session, "ops@test.local", current)).access_token
    # The same code twice (replay) is refused.
    with pytest.raises(AppError):
        await _login(db_session, "ops@test.local", current)

    # A recovery code works once.
    assert (await _login(db_session, "ops@test.local", recovery[0])).access_token
    with pytest.raises(AppError):
        await _login(db_session, "ops@test.local", recovery[0])

    events = [e["event"] for e in _env]
    assert "auth.2fa.enabled" in events
    assert "auth.login.totp_failed" in events
    assert events.count("auth.login.success") >= 3


@pytest.mark.asyncio
async def test_required_2fa_blocks_the_admin_until_enrolment(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    user_id = await _admin(db_session)
    monkeypatch.setattr(settings, "ADMIN_2FA_REQUIRED", True)
    user = await db_session.get(User, user_id)
    assert user is not None

    with pytest.raises(AppError) as refused:
        await deps.get_current_active_superuser(user)
    assert refused.value.code == "auth.totp.enrollment_required"
    assert await deps.get_current_superuser_enrolling(user) is user
    status = await routes.get_status(user)
    assert status.required is True and status.enabled is False

    await _enrol(db_session, user_id)
    user = await db_session.get(User, user_id)
    assert user is not None
    assert await deps.get_current_active_superuser(user) is user


@pytest.mark.asyncio
async def test_disable_needs_password_and_code(db_session: AsyncSession) -> None:
    user_id = await _admin(db_session)
    secret, recovery = await _enrol(db_session, user_id)
    await _open_session(db_session, user_id)
    user = await db_session.get(User, user_id)
    assert user is not None

    with pytest.raises(AppError):
        await routes.disable(
            _request(),
            routes.TwoFactorDisable(code=recovery[1], password="wrong"),
            db_session,
            user,
        )
    status = await routes.disable(
        _request(),
        routes.TwoFactorDisable(code=recovery[1], password=PASSWORD),
        db_session,
        user,
    )
    assert status.enabled is False
    user = await db_session.get(User, user_id)
    assert user is not None and user.totp_secret_encrypted is None
    # Audit 2026-11, S4: the stored sessions end with the 2FA.
    assert await _active_sessions(db_session, user_id) == 0


@pytest.mark.asyncio
async def test_an_admin_resets_another_admins_2fa_but_not_their_own(
    db_session: AsyncSession,
) -> None:
    first = await _admin(db_session, "first@test.local")
    second = await _admin(db_session, "second@test.local")
    await _enrol(db_session, second)

    await _open_session(db_session, second)
    assert await _active_sessions(db_session, second) == 1

    actor = cast(User, SimpleNamespace(id=first))
    item = await reset_two_factor(second, db_session, actor)
    assert item.totp_enabled is False
    # Audit 2026-11, S4: a stolen session does not survive the reset.
    assert await _active_sessions(db_session, second) == 0

    with pytest.raises(AppError) as refused:
        await reset_two_factor(first, db_session, actor)
    assert refused.value.code == "auth.totp.reset_self"


@pytest.mark.asyncio
async def test_customers_never_meet_the_second_factor(db_session: AsyncSession) -> None:
    customer = User(
        email="client@test.local",
        hashed_password=get_password_hash(PASSWORD),
        is_active=True,
    )
    db_session.add(customer)
    await db_session.commit()
    assert (await _login(db_session, "client@test.local")).access_token


@pytest.mark.asyncio
async def test_an_unenrolled_admin_has_no_power_on_any_route(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Audit 2026-11, S5: the 2FA rule lived in ``CurrentSuperUser`` only.
    The routes checking ``is_superuser`` by hand (and ``BaseRouter``) took a
    stolen admin password without its second factor, and the internal fields
    (cost, margin) were revealed first. The rule now sits in
    ``get_current_user``; the profile and the enrolment stay reachable."""
    from app.core import security
    from app.core.field_visibility import internal_fields_revealed

    user_id = await _admin(db_session)
    monkeypatch.setattr(settings, "ADMIN_2FA_REQUIRED", True)
    user = await db_session.get(User, user_id)
    assert user is not None
    token = security.create_access_token(
        user_id, expires_delta=timedelta(minutes=5), stamp=user.security_stamp
    )

    with pytest.raises(AppError) as refused:
        await deps.get_current_user(db_session, token)
    assert refused.value.code == "auth.totp.enrollment_required"
    assert not internal_fields_revealed()

    # Who is signed in, and the enrolment itself, remain reachable.
    me = await deps.get_current_user_enrolling(db_session, token)
    assert await deps.get_current_superuser_enrolling(me) is me
    assert not internal_fields_revealed()

    await _enrol(db_session, user_id)
    user = await db_session.get(User, user_id)
    assert user is not None
    token = security.create_access_token(
        user_id, expires_delta=timedelta(minutes=5), stamp=user.security_stamp
    )
    assert (await deps.get_current_user(db_session, token)).id == user_id
