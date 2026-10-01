"""Time-based one-time passwords (RFC 6238), as authenticator apps compute them.

HMAC-SHA1, 30-second steps, 6 digits — the defaults every app (Google
Authenticator, Microsoft Authenticator, 1Password, Aegis…) uses when the
``otpauth://`` URI says nothing else. :func:`matching_step` accepts the
previous and next step too (clock drift) and returns the step it matched, so
the caller can refuse a code already used (replay).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time
from urllib.parse import quote, urlencode

DIGITS = 6
PERIOD_SECONDS = 30
#: Steps accepted on each side of the current one (±30 s of clock drift).
DRIFT_STEPS = 1


def generate_secret() -> str:
    """A new shared secret: 160 random bits, base32 without padding."""
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def _key(secret: str) -> bytes:
    cleaned = secret.strip().replace(" ", "").upper()
    return base64.b32decode(cleaned + "=" * (-len(cleaned) % 8))


def code_at(secret: str, step: int) -> str:
    """The code of time step ``step`` (RFC 4226 dynamic truncation)."""
    digest = hmac.new(_key(secret), struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(value % 10**DIGITS).zfill(DIGITS)


def current_step(at: float | None = None) -> int:
    return int((time.time() if at is None else at) // PERIOD_SECONDS)


def matching_step(secret: str, code: str, *, at: float | None = None) -> int | None:
    """The time step ``code`` belongs to (within the drift window), or None."""
    candidate = "".join(ch for ch in code if ch.isdigit())
    if len(candidate) != DIGITS:
        return None
    now = current_step(at)
    for step in range(now - DRIFT_STEPS, now + DRIFT_STEPS + 1):
        if hmac.compare_digest(code_at(secret, step), candidate):
            return step
    return None


def provisioning_uri(secret: str, *, account: str, issuer: str) -> str:
    """``otpauth://totp/…`` URI, the content of the QR code apps scan."""
    label = quote(f"{issuer}:{account}")
    query = urlencode(
        {
            "secret": secret,
            "issuer": issuer,
            "algorithm": "SHA1",
            "digits": DIGITS,
            "period": PERIOD_SECONDS,
        }
    )
    return f"otpauth://totp/{label}?{query}"


__all__ = [
    "DIGITS",
    "PERIOD_SECONDS",
    "code_at",
    "current_step",
    "generate_secret",
    "matching_step",
    "provisioning_uri",
]
