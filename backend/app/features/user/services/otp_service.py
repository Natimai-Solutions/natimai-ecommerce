"""Email-OTP signup helpers (Redis-backed, ephemeral).

Redis key schema (all TTL'd, no PII persisted in the DB):
    otp:{email}          → JSON {"code": "123456", "attempts": N}   TTL 10 min
    otp_rate:{email}     → send counter (max 3 / 10 min)            TTL 10 min
    signup_token:{uuid}  → the verified email (single-use)          TTL 15 min

The Redis client is passed in (dependency-injected) so the endpoints use the
app's ``RedisDep`` and tests can pass a fake client.
"""

from __future__ import annotations

import json
import secrets
import string
import uuid

import redis.asyncio as redis

from app.core.errors import AppError

OTP_TTL_SECONDS = 600  # 10 minutes
OTP_MAX_SENDS = 3  # per email per OTP_TTL window
OTP_MAX_ATTEMPTS = 5  # wrong-code attempts before the OTP is burned
SIGNUP_TOKEN_TTL_SECONDS = 900  # 15 minutes
OTP_VALID_MINUTES = OTP_TTL_SECONDS // 60


def _generate_code() -> str:
    """A cryptographically-random 6-digit code."""
    return "".join(secrets.choice(string.digits) for _ in range(6))


def _as_str(raw: bytes | str) -> str:
    return raw.decode() if isinstance(raw, bytes) else str(raw)


async def create_otp(r: redis.Redis, email: str) -> str:
    """Generate + store an OTP for ``email`` (rate-limited). Returns the code."""
    email_lower = email.lower()

    rate_key = f"otp_rate:{email_lower}"
    sends = await r.incr(rate_key)
    if sends == 1:
        await r.expire(rate_key, OTP_TTL_SECONDS)
    if sends > OTP_MAX_SENDS:
        raise AppError(
            code="otp.rate_limit",
            status_code=429,
            message="Trop de demandes de code. Réessayez dans quelques minutes.",
        )

    code = _generate_code()
    await r.set(
        f"otp:{email_lower}",
        json.dumps({"code": code, "attempts": 0}),
        ex=OTP_TTL_SECONDS,
    )
    return code


async def verify_otp(r: redis.Redis, *, email: str, code: str) -> str:
    """Validate ``code`` for ``email``. On success, burn the OTP and return a
    single-use ``signup_token``. Raises AppError on expiry / wrong / locked."""
    email_lower = email.lower()
    otp_key = f"otp:{email_lower}"

    raw = await r.get(otp_key)
    if raw is None:
        raise AppError(
            code="otp.expired",
            status_code=400,
            message="Code expiré ou introuvable. Demandez un nouveau code.",
        )

    data = json.loads(_as_str(raw))
    attempts = int(data.get("attempts", 0)) + 1
    if attempts > OTP_MAX_ATTEMPTS:
        await r.delete(otp_key)
        raise AppError(
            code="otp.too_many_attempts",
            status_code=400,
            message="Trop de tentatives. Demandez un nouveau code.",
        )

    if data.get("code") != code.strip():
        data["attempts"] = attempts
        ttl = await r.ttl(otp_key)
        await r.set(otp_key, json.dumps(data), ex=max(int(ttl), 1))
        raise AppError(
            code="otp.invalid_code",
            status_code=400,
            message="Code invalide.",
        )

    await r.delete(otp_key)
    token = str(uuid.uuid4())
    await r.set(f"signup_token:{token}", email_lower, ex=SIGNUP_TOKEN_TTL_SECONDS)
    return token


async def consume_signup_token(r: redis.Redis, token: str) -> str:
    """Atomically read-and-delete a signup token, returning the verified email."""
    raw = await r.getdel(f"signup_token:{token}")
    if raw is None:
        raise AppError(
            code="otp.invalid_signup_token",
            status_code=400,
            message="Session d'inscription expirée. Recommencez l'inscription.",
        )
    return _as_str(raw)
