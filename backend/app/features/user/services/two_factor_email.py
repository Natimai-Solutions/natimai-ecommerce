"""E-mail confirmation of an administrator's 2FA enrolment (audit 2026-11, S5).

Without it, a stolen administrator password, before its owner enrolled (or
after a 2FA reset), let the thief enrol *their* authenticator and hold the
back office for good. ``/setup`` now e-mails a one-time code to the account's
address; ``/confirm`` takes it along with the authenticator's code. The code
lives in Redis, hashed, for :data:`CODE_TTL_MINUTES`, and dies after
:data:`MAX_ATTEMPTS` wrong tries (a new ``/setup`` sends another).
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import secrets
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

CODE_LENGTH = 8
CODE_TTL_MINUTES = 15
MAX_ATTEMPTS = 5


def _keys(user_id: uuid.UUID) -> tuple[str, str]:
    return f"2fa:enrol:{user_id}", f"2fa:enrol:tries:{user_id}"


def _digest(user_id: uuid.UUID, code: str) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"{user_id}:{code.strip()}".encode(),
        hashlib.sha256,
    ).hexdigest()


def new_code() -> str:
    """Eight digits: read in an e-mail, typed in the back office."""
    return "".join(secrets.choice("0123456789") for _ in range(CODE_LENGTH))


async def _redis(operation: Any) -> Any:
    try:
        return await operation
    except Exception as exc:  # noqa: BLE001 — no store, no enrolment
        raise AppError(
            code="rate_limit.unavailable",
            status_code=503,
            message="Service momentanément indisponible : réessayez dans un instant.",
            details={},
        ) from exc


async def send_code(session: AsyncSession, *, user_id: uuid.UUID, email: str) -> None:
    """Store a fresh code (replacing a pending one) and e-mail it. No commit."""
    from app.core.rate_limit import shared_redis
    from app.features.notification.email_renderer import render_email
    from app.features.notification.mailer import queue_email

    code = new_code()
    code_key, tries_key = _keys(user_id)
    ttl = CODE_TTL_MINUTES * 60

    async def _store() -> Any:
        async with shared_redis().pipeline(transaction=True) as pipe:
            pipe.set(code_key, _digest(user_id, code), ex=ttl)
            pipe.delete(tries_key)
            return await pipe.execute()

    await _redis(_store())
    rendered = render_email(
        "two_factor_enrolment",
        code=code,
        valid_minutes=CODE_TTL_MINUTES,
        shop_name=runtime_settings.peek("shop_name"),
    )
    await queue_email(
        session,
        recipient=email,
        subject=rendered.subject,
        text=rendered.text,
        html=rendered.html,
        event_type="auth.2fa.enrolment_code",
        resendable=False,  # carries a valid code
    )
    if settings.ENVIRONMENT == "local":
        # Without a mailer the code would exist nowhere. Never logged elsewhere.
        logger.info("[DEV] 2FA enrolment code for %s = %s", email, code)


async def check_code(user_id: uuid.UUID, code: str | None) -> None:
    """Accept the e-mailed code once, or raise ``auth.2fa.email_code_invalid``."""
    from app.core.rate_limit import shared_redis

    redis = shared_redis()
    code_key, tries_key = _keys(user_id)
    stored = await _redis(redis.get(code_key))
    if stored is None:
        raise AppError(
            code="auth.2fa.email_code_expired",
            status_code=400,
            message="Code e-mail expiré : recommencez l'activation.",
            details={},
        )
    expected = stored.decode() if isinstance(stored, bytes) else str(stored)
    if code and hmac.compare_digest(expected, _digest(user_id, code)):
        await _redis(redis.delete(code_key, tries_key))
        return
    tries = int(await _redis(redis.incr(tries_key)))
    await _redis(redis.expire(tries_key, CODE_TTL_MINUTES * 60))
    if tries >= MAX_ATTEMPTS:
        await _redis(redis.delete(code_key, tries_key))
    raise AppError(
        code="auth.2fa.email_code_invalid",
        status_code=400,
        message="Code reçu par e-mail incorrect.",
        details={"attempts_left": max(MAX_ATTEMPTS - tries, 0)},
    )
