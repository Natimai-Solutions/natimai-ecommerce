"""Signed order-tracking links: follow an order without signing in.

The token is an HMAC of the order id under ``SECRET_KEY`` — nothing stored:
like a parcel number, whoever holds the link the customer received can read
that one order's progress, and only that. The link stops working
``TRACKING_LINK_DAYS`` after the order: e-mails get forwarded, and an old
order's address has nothing to do in an inbox years later.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from datetime import UTC, datetime, timedelta

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


#: How long the signed link of an order works (its account view stays).
TRACKING_LINK_DAYS = 180


def tracking_link_still_valid(
    created_at: datetime | None, *, now: datetime | None = None
) -> bool:
    """Whether the link of an order placed at ``created_at`` still works."""
    if created_at is None:
        return True
    if created_at.tzinfo is None:
        created_at = created_at.replace(tzinfo=UTC)
    return (now or datetime.now(UTC)) - created_at <= timedelta(days=TRACKING_LINK_DAYS)


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
    "TRACKING_LINK_DAYS",
    "order_tracking_token",
    "tracking_link_still_valid",
    "order_tracking_url",
    "tracking_url_from_payload",
    "verify_order_tracking_token",
]
