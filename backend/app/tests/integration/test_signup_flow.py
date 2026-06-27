"""Integration tests for the email-OTP signup completion (real DB)."""

import uuid

import pytest
from fastapi import Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.signup import (
    CompleteSignupRequest,
    SendOtpRequest,
    complete_signup,
    send_otp,
)
from app.core.errors import AppError
from app.features.user.crud.user import crud_user
from app.features.user.models.user import User
from app.features.user.services.otp_service import create_otp, verify_otp
from app.tests.utils.fake_redis import fake_redis


@pytest.mark.asyncio
async def test_complete_signup_creates_verified_logged_in_account(
    db_session: AsyncSession,
) -> None:
    r = fake_redis()
    email = f"signup+{uuid.uuid4().hex[:8]}@example.com"
    code = await create_otp(r, email)
    token = await verify_otp(r, email=email, code=code)

    response = Response()
    result = await complete_signup(
        body=CompleteSignupRequest(
            signup_token=token, password="s3cretpassword", full_name="New Customer"
        ),
        session=db_session,
        redis=r,
        response=response,
    )

    assert result.access_token
    # A refresh cookie was issued.
    assert any(
        key == b"set-cookie" and b"refresh_token" in value
        for key, value in response.raw_headers
    )

    user = await crud_user.get_by_email(db_session, email=email)
    assert user is not None
    assert user.is_verified is True
    # The password actually authenticates (it was hashed, not stored in clear).
    assert (
        await crud_user.authenticate(db_session, email=email, password="s3cretpassword")
        is not None
    )


@pytest.mark.asyncio
async def test_send_otp_refuses_existing_email(db_session: AsyncSession) -> None:
    email = f"existing+{uuid.uuid4().hex[:8]}@example.com"
    db_session.add(User(email=email, is_active=True, hashed_password="x"))
    await db_session.flush()

    with pytest.raises(AppError) as exc:
        await send_otp(
            body=SendOtpRequest(email=email), session=db_session, redis=fake_redis()
        )
    assert exc.value.code == "signup.email_exists"
