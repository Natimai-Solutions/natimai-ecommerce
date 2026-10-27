"""Unit tests for the email-OTP signup service (in-memory fake Redis)."""

import pytest

from app.core.errors import AppError
from app.features.user.services.otp_service import (
    OTP_MAX_ATTEMPTS,
    OTP_MAX_SENDS,
    consume_signup_token,
    create_otp,
    verify_otp,
)
from app.tests.utils.fake_redis import fake_redis

_EMAIL = "newcustomer@test.local"


@pytest.mark.asyncio
async def test_create_otp_returns_six_digit_code() -> None:
    code = await create_otp(fake_redis(), _EMAIL)
    assert len(code) == 6
    assert code.isdigit()


@pytest.mark.asyncio
async def test_create_otp_enforces_send_rate_limit() -> None:
    r = fake_redis()
    for _ in range(OTP_MAX_SENDS):
        await create_otp(r, _EMAIL)
    with pytest.raises(AppError) as exc:
        await create_otp(r, _EMAIL)
    assert exc.value.status_code == 429
    assert exc.value.code == "otp.rate_limit"


@pytest.mark.asyncio
async def test_verify_valid_code_returns_single_use_token() -> None:
    r = fake_redis()
    code = await create_otp(r, _EMAIL)

    token = await verify_otp(r, email=_EMAIL, code=code)
    assert token

    assert await consume_signup_token(r, token) == _EMAIL
    # the signup token is single-use
    with pytest.raises(AppError) as exc:
        await consume_signup_token(r, token)
    assert exc.value.code == "otp.invalid_signup_token"


@pytest.mark.asyncio
async def test_verify_wrong_code_is_rejected() -> None:
    r = fake_redis()
    code = await create_otp(r, _EMAIL)
    wrong = "000000" if code != "000000" else "111111"
    with pytest.raises(AppError) as exc:
        await verify_otp(r, email=_EMAIL, code=wrong)
    assert exc.value.code == "otp.invalid_code"


@pytest.mark.asyncio
async def test_verify_without_otp_is_expired() -> None:
    with pytest.raises(AppError) as exc:
        await verify_otp(fake_redis(), email=_EMAIL, code="123456")
    assert exc.value.code == "otp.expired"


@pytest.mark.asyncio
async def test_verify_locks_after_too_many_attempts() -> None:
    r = fake_redis()
    code = await create_otp(r, _EMAIL)
    wrong = "000000" if code != "000000" else "111111"

    for _ in range(OTP_MAX_ATTEMPTS):
        with pytest.raises(AppError) as exc:
            await verify_otp(r, email=_EMAIL, code=wrong)
        assert exc.value.code == "otp.invalid_code"

    with pytest.raises(AppError) as exc:
        await verify_otp(r, email=_EMAIL, code=wrong)
    assert exc.value.code == "otp.too_many_attempts"


@pytest.mark.asyncio
async def test_parallel_guesses_each_spend_an_attempt() -> None:
    """A burst of simultaneous guesses used to read the same counter: each
    one now takes an attempt (INCR), so the budget holds."""
    import asyncio

    r = fake_redis()
    code = await create_otp(r, _EMAIL)
    wrong = "000000" if code != "000000" else "111111"

    outcomes = await asyncio.gather(
        *(verify_otp(r, email=_EMAIL, code=wrong) for _ in range(OTP_MAX_ATTEMPTS + 3)),
        return_exceptions=True,
    )

    codes = [o.code for o in outcomes if isinstance(o, AppError)]
    assert codes.count("otp.invalid_code") == OTP_MAX_ATTEMPTS
    assert "otp.too_many_attempts" in codes
    # The code is gone: even the right one is refused now.
    with pytest.raises(AppError):
        await verify_otp(r, email=_EMAIL, code=code)
