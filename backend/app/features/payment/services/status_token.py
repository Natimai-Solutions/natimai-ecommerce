"""Signed token to read a payment's status without a session (audit 2026-11).

3-D Secure often ends in the bank's app or another browser: the customer
lands on the return page signed out, and ``GET /payments/me/{id}`` (session
required) answered 401 — the page then reported a timeout for a payment that
went through. The token travels in the return URL; it only unlocks the
status of that one payment (no personal data).
"""

from __future__ import annotations

import hashlib
import hmac
import uuid

from app.core.config import settings


def payment_status_token(payment_id: uuid.UUID) -> str:
    return hmac.new(
        settings.SECRET_KEY.encode(),
        f"payment-status:{payment_id}".encode(),
        hashlib.sha256,
    ).hexdigest()[:32]


def check_payment_status_token(payment_id: uuid.UUID, token: str | None) -> bool:
    return bool(token) and hmac.compare_digest(
        payment_status_token(payment_id), str(token)
    )
