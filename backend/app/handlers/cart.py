"""Outbox handler: the « panier oublié » reminder e-mail (Z3)."""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.cart.models.cart import Cart
from app.features.cart.services.abandonment import (
    EVENT_CART_ABANDONED,
    marketing_emails_allowed,
)
from app.features.notification.email_renderer import render_email
from app.handlers.order import _resolve_user_from_payload, _send_order_email, _shop_name
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)


@outbox_handler(EVENT_CART_ABANDONED)
async def on_cart_abandoned(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Send the reminder, unless the cart moved on or the customer opted out.

    The sweep already stamped the cart, so a replay of this event can only
    come from the outbox's at-least-once delivery: the checks below make the
    mail itself safe to replay (an ordered cart, an opted-out customer).
    """
    raw_cart_id = payload.get("cart_id")
    raw_user_id = payload.get("user_id")
    try:
        cart_id = uuid.UUID(str(raw_cart_id))
        user_id = uuid.UUID(str(raw_user_id))
    except (TypeError, ValueError):
        logger.warning("cart reminder: malformed payload %r, skipping", payload)
        return

    cart = await session.get(Cart, cart_id)
    if cart is None or cart.is_checked_out or not cart.is_active:
        logger.info("cart reminder: cart %s gone or ordered, skipping", cart_id)
        return
    if not await marketing_emails_allowed(session, user_id):
        logger.info("cart reminder: user %s opted out, skipping", user_id)
        return

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""
    items = [dict(line) for line in payload.get("items") or []]
    if not items:
        logger.info("cart reminder: cart %s has no lines, skipping", cart_id)
        return

    email = render_email(
        "cart_abandoned",
        full_name=full_name or "client",
        items=items,
        total_amount=payload.get("total_amount", ""),
        currency=payload.get("currency", ""),
        cart_url=f"{settings.FRONTEND_HOST.rstrip('/')}/panier",
        preferences_url=f"{settings.FRONTEND_HOST.rstrip('/')}/mon-compte",
        shop_name=_shop_name(),
    )
    delivered = await _send_order_email(
        session,
        user_id_raw=str(user_id),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_CART_ABANDONED,
        payload=payload,
    )
    if not delivered:
        # Marketing, not a legal document: log and stop, never retry forever.
        logger.warning("cart reminder: e-mail for cart %s not delivered", cart_id)
