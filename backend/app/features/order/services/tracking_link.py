"""Signed order-tracking links: follow an order without signing in.

The token is an HMAC of the order id under ``SECRET_KEY`` — nothing stored,
nothing to expire: like a parcel number, whoever holds the link the customer
received can read that one order's progress, and only that.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid

from app.core.config import settings


def order_tracking_token(order_id: uuid.UUID) -> str:
    """The signature of ``order_id`` (URL-safe, 32 chars)."""
    digest = hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        f"order-tracking:{order_id}".encode(),
        hashlib.sha256,
    ).digest()
    return base64.urlsafe_b64encode(digest[:24]).rstrip(b"=").decode("ascii")


def verify_order_tracking_token(order_id: uuid.UUID, token: str | None) -> bool:
    """Constant-time check of a token against the order id."""
    if not token:
        return False
    return hmac.compare_digest(order_tracking_token(order_id), token.strip())


def order_tracking_url(order_id: uuid.UUID) -> str:
    """The storefront tracking page, signed for this order."""
    base = settings.FRONTEND_HOST.rstrip("/")
    return f"{base}/suivi/{order_id}?t={order_tracking_token(order_id)}"


def tracking_url_from_payload(order_id_raw: object) -> str | None:
    """`order_tracking_url` for an event payload's id; None when unusable,
    so an e-mail still goes out without the link."""
    try:
        return order_tracking_url(uuid.UUID(str(order_id_raw)))
    except (TypeError, ValueError):
        return None


__all__ = [
    "order_tracking_token",
    "order_tracking_url",
    "tracking_url_from_payload",
    "verify_order_tracking_token",
]
