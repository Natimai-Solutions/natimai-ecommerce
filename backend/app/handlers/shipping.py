"""Outbox handlers for shipping / tracking events (customer-facing emails).

Handlers:
- on_tracking_status_changed → email for 'progress', 'shipped' and 'delivered'
  milestones. Respects user.preference.notification_shipping_steps.

Email bodies live in app/templates/email/<lang>/ and are rendered via
app.features.notification.email_renderer.render_email.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.features.notification.email_renderer import RenderedEmail, render_email
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.order.models.order import Order
from app.features.order.services.order_number import resolve_order_ref
from app.features.order.services.tracking_link import tracking_url_from_payload
from app.features.user.crud.user_preference import get_preference_for_user
from app.features.user.models.user import User
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)

_SHIPPED_CODES = {"shipped", "expedie", "en_transit", "in_transit"}
_DELIVERED_CODES = {"delivered", "livre", "livré", "delivered_to_customer"}
_PROGRESS_CODES = {"in_progress", "en_cours"}


async def _resolve_order_user(
    session: AsyncSession, order_id_raw: str | None
) -> User | None:
    """Return the User associated with an order."""
    if not order_id_raw:
        return None
    try:
        oid = uuid.UUID(str(order_id_raw))
    except (TypeError, ValueError):
        return None

    order = await session.get(Order, oid)
    if order is None or order.user_id is None:
        return None
    return await session.get(User, order.user_id)


async def _send_shipping_email(
    session: AsyncSession,
    *,
    user: User,
    subject: str,
    text: str,
    html: str,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Check notification preference and send the email if enabled."""
    if not await runtime_settings.get("notifications_email_enabled", session):
        return

    pref = await get_preference_for_user(session, user_id=user.id)
    if pref is not None and not pref.notification_shipping_steps:
        return

    try:
        provider = get_notification_provider(
            settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
        )
    except UnknownNotificationProviderError:
        provider = get_notification_provider("noop")

    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient=user.email,
            subject=subject,
            text=text,
            html=html,
            metadata={"event_type": event_type, "payload": payload},
        )
    )
    if not result.delivered:
        logger.warning(
            "shipping email failed: event=%s user=%s provider=%s error=%s",
            event_type,
            user.id,
            result.provider_code,
            result.error,
        )


@outbox_handler("tracking.status_changed")
async def on_tracking_status_changed(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send shipping notification email on progress/shipped/delivered milestones."""
    status_code = (payload.get("status_code") or "").strip().lower()
    order_id_raw = payload.get("order_id")
    tracking_ref = payload.get("tracking_ref")
    estimated_delivery = payload.get("estimated_delivery")

    if (
        status_code not in _SHIPPED_CODES
        and status_code not in _DELIVERED_CODES
        and status_code not in _PROGRESS_CODES
    ):
        return

    user = await _resolve_order_user(session, order_id_raw)
    if user is None or not user.email:
        logger.warning(
            "tracking email: could not resolve user for order %s", order_id_raw
        )
        return

    full_name = user.full_name or user.email or ""
    shop_name = getattr(settings, "SHOP_NAME", "Natimai")
    order_id_display = str(order_id_raw or "")
    # Customer-facing reference (M5): CMD-2026-00042, short-ref fallback.
    order_ref = await resolve_order_ref(session, payload)
    tracking_url = tracking_url_from_payload(order_id_raw)

    email: RenderedEmail
    if status_code in _SHIPPED_CODES:
        email = render_email(
            "shipping_shipped",
            full_name=full_name or "client",
            order_id=order_id_display,
            order_ref=order_ref,
            tracking_ref=tracking_ref or "",
            estimated_delivery=estimated_delivery or "",
            tracking_url=tracking_url,
            shop_name=shop_name,
        )
        event_label = "tracking.shipped"
    elif status_code in _DELIVERED_CODES:
        email = render_email(
            "shipping_delivered",
            full_name=full_name or "client",
            order_id=order_id_display,
            order_ref=order_ref,
            tracking_url=tracking_url,
            shop_name=shop_name,
        )
        event_label = "tracking.delivered"
    else:  # progress milestone (next-leg activation)
        email = render_email(
            "shipping_progress",
            full_name=full_name or "client",
            order_id=order_id_display,
            order_ref=order_ref,
            tracking_ref=tracking_ref or "",
            tracking_url=tracking_url,
            shop_name=shop_name,
        )
        event_label = "tracking.progress"

    await _send_shipping_email(
        session,
        user=user,
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=event_label,
        payload=payload,
    )
