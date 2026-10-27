"""Integration (real DB): ordering without an account opens a passwordless
« guest » account and its session; the address owner takes it over later."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock

import pytest
from fastapi import Request, Response
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import signup as signup_module
from app.api.routes.password_reset import ResetPasswordRequest, reset_password
from app.api.routes.signup import (
    CompleteSignupRequest,
    GuestStartRequest,
    SendOtpRequest,
    complete_signup,
    send_my_guest_activation_link,
    send_otp,
    start_guest_checkout,
)
from app.api.routes.users_me import get_my_profile
from app.core.errors import AppError
from app.core.security import get_password_hash, hash_reset_token
from app.features.notification.models.email_log import EmailLog
from app.features.user.crud.user import crud_user
from app.features.user.models.refresh_token import UserRefreshToken
from app.features.user.models.user import User
from app.features.user.services.otp_service import create_otp, verify_otp
from app.tests.utils.fake_redis import fake_redis


def _request() -> Request:
    return cast(
        Request, SimpleNamespace(headers={}, client=SimpleNamespace(host="10.0.0.1"))
    )


def _email() -> str:
    return f"invite+{uuid.uuid4().hex[:8]}@example.com"


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(signup_module, "hit_rate_limit", AsyncMock(return_value=False))


async def _start(db_session: AsyncSession, email: str) -> Response:
    response = Response()
    token = await start_guest_checkout(
        GuestStartRequest(email=email.upper(), full_name="  Hina Teriitahi ", phone=""),
        _request(),
        db_session,
        response,
    )
    assert token.access_token
    return response


async def _activation_mails(db_session: AsyncSession, email: str) -> int:
    rows = await db_session.exec(
        select(EmailLog).where(
            col(EmailLog.recipient) == email,
            col(EmailLog.event_type) == "user.guest_activation",
        )
    )
    return len(rows.all())


@pytest.mark.asyncio
async def test_a_guest_orders_then_chooses_a_password(
    db_session: AsyncSession,
) -> None:
    email = _email()
    response = await _start(db_session, email)
    assert any(
        key == b"set-cookie" and b"refresh_token" in value
        for key, value in response.raw_headers
    )

    guest = await crud_user.get_by_email(db_session, email=email)
    assert guest is not None
    assert guest.is_guest is True and guest.is_verified is False
    assert guest.full_name == "Hina Teriitahi" and guest.phone is None
    # Nobody can sign in with a password on it.
    assert await crud_user.authenticate(db_session, email=email, password="") is None
    await db_session.refresh(guest)
    profile = await get_my_profile(guest)
    assert profile.is_guest is True

    # « Créer mon compte » after the order: the link is e-mailed…
    await send_my_guest_activation_link(db_session, guest)
    assert await _activation_mails(db_session, email) == 1
    guest = await crud_user.get_by_email(db_session, email=email)
    assert guest is not None and guest.password_reset_token is not None

    # …and following it makes a customer account (same page as a reset).
    token = "lien-recu-par-email-" + uuid.uuid4().hex
    guest.password_reset_token = hash_reset_token(token)
    db_session.add(guest)
    await db_session.commit()
    await reset_password(
        ResetPasswordRequest(token=token, password="mon-mot-de-passe"), db_session
    )
    customer = await crud_user.get_by_email(db_session, email=email)
    assert customer is not None
    assert customer.is_guest is False and customer.is_verified is True
    assert (
        await crud_user.authenticate(
            db_session, email=email, password="mon-mot-de-passe"
        )
        is not None
    )
    await db_session.refresh(customer)
    with pytest.raises(AppError) as refused:
        await send_my_guest_activation_link(db_session, customer)
    assert refused.value.code == "signup.guest.not_guest"


@pytest.mark.asyncio
async def test_a_known_address_never_opens_a_session(
    db_session: AsyncSession,
) -> None:
    # A customer with a password: sign in.
    customer_email = _email()
    db_session.add(
        User(
            email=customer_email,
            is_active=True,
            is_verified=True,
            hashed_password=get_password_hash("mot-de-passe-client"),
        )
    )
    await db_session.commit()
    with pytest.raises(AppError) as refused:
        await _start(db_session, customer_email)
    assert refused.value.code == "signup.guest.account_exists"
    assert refused.value.status_code == 409
    assert refused.value.details == {"reason": "account"}
    assert await _activation_mails(db_session, customer_email) == 0

    # An earlier guest: no session either, the take-over link goes to the box.
    guest_email = _email()
    await _start(db_session, guest_email)
    with pytest.raises(AppError) as again:
        await _start(db_session, guest_email)
    assert again.value.details == {"reason": "guest"}
    assert await _activation_mails(db_session, guest_email) == 1


@pytest.mark.asyncio
async def test_signing_up_with_the_address_takes_the_guest_account_over(
    db_session: AsyncSession,
) -> None:
    email = _email()
    await _start(db_session, email)
    guest = await crud_user.get_by_email(db_session, email=email)
    assert guest is not None
    guest_id = guest.id

    r = fake_redis()
    # The signup accepts the address of a guest account…
    await send_otp(
        body=SendOtpRequest(email=email),
        request=_request(),
        session=db_session,
        redis=r,
    )
    code = await create_otp(r, email)
    signup_token = await verify_otp(r, email=email, code=code)
    await complete_signup(
        body=CompleteSignupRequest(
            signup_token=signup_token, password="mon-mot-de-passe", full_name=None
        ),
        session=db_session,
        redis=r,
        response=Response(),
    )

    # …and keeps it (its orders with it), now a customer account.
    user = await crud_user.get_by_email(db_session, email=email)
    assert user is not None and user.id == guest_id
    assert user.is_guest is False and user.is_verified is True
    assert user.full_name == "Hina Teriitahi"
    # The session opened at checkout is closed, the signup's is open.
    tokens = (
        await db_session.exec(
            select(UserRefreshToken).where(col(UserRefreshToken.user_id) == guest_id)
        )
    ).all()
    assert len(tokens) == 2
    assert sorted(t.revoked_reason or "" for t in tokens) == ["", "guest_claimed"]
