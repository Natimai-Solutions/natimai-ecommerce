"""Outbox handlers for order events (customer-facing emails).

Handlers:
- on_order_created    → 'Commande reçue' email after checkout
- on_payment_captured → 'Paiement validé' email to the customer
- on_payment_rejected → 'Paiement échoué' email to the customer
- on_payment_refunded → 'Remboursement effectué' email to the customer

Email bodies live in app/templates/email/<lang>/ and are rendered via
app.features.notification.email_renderer.render_email.

Admin/support technical notifications for payment events are handled
separately in app.features.payment.services.notifications.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.invoice.models.invoice import Invoice
from app.features.notification.email_renderer import render_email
from app.features.notification.providers import (
    NotificationMessage,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.order.services.order_number import resolve_order_ref
from app.features.user.models.user import User
from app.outbox.decorators import outbox_handler

logger = logging.getLogger(__name__)

EVENT_ORDER_CREATED = "order.created"
EVENT_PAYMENT_CAPTURED = "payment.captured"
EVENT_PAYMENT_REJECTED = "payment.rejected"
EVENT_PAYMENT_REFUNDED = "payment.refunded"
EVENT_INVOICE_ISSUED = "invoice.issued"


def _shop_name() -> str:
    return getattr(settings, "SHOP_NAME", "Natimai")


async def _send_order_email(
    session: AsyncSession,
    *,
    user_id_raw: str | None,
    subject: str,
    text: str,
    html: str,
    event_type: str,
    payload: dict[str, Any],
) -> bool:
    """Resolve user email and dispatch the notification if enabled.

    Returns whether the message actually reached the provider, so a caller
    that must not lose the notification (the invoice) can fail and be retried.
    """
    if not settings.PAYMENT_NOTIFICATIONS_EMAIL_ENABLED:
        return False

    if not user_id_raw:
        logger.warning("order email: missing user_id in payload, skipping")
        return False

    try:
        user_uuid = uuid.UUID(str(user_id_raw))
    except (TypeError, ValueError):
        logger.warning("order email: invalid user_id %r, skipping", user_id_raw)
        return False

    user = await session.get(User, user_uuid)
    if user is None or not user.email:
        logger.warning("order email: user %s not found or has no email", user_uuid)
        return False

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
            "order email failed: event=%s user=%s provider=%s error=%s",
            event_type,
            user_uuid,
            result.provider_code,
            result.error,
        )
    return bool(result.delivered)


async def _resolve_user_from_payload(
    session: AsyncSession, payload: dict[str, Any]
) -> User | None:
    raw = payload.get("user_id")
    if not raw:
        return None
    try:
        return await session.get(User, uuid.UUID(str(raw)))
    except (TypeError, ValueError):
        return None


# Customer-facing order reference (M5) — shared with the shipping handlers.
_resolve_order_ref = resolve_order_ref


@outbox_handler(EVENT_ORDER_CREATED)
async def on_order_created(session: AsyncSession, payload: dict[str, Any]) -> None:
    """Send 'Commande reçue' email to the customer after checkout."""
    logger.info(
        "Order created: order_id=%s user_id=%s",
        payload.get("order_id"),
        payload.get("user_id"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "order_created",
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        total_amount=payload.get("total_amount", ""),
        currency=payload.get("currency", ""),
        item_count=payload.get("item_count", ""),
        shop_name=_shop_name(),
    )

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_ORDER_CREATED,
        payload=payload,
    )


@outbox_handler(EVENT_PAYMENT_CAPTURED)
async def on_payment_captured_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send 'Paiement validé' HTML email to the customer."""
    logger.info(
        "Payment captured (customer email): order_id=%s user_id=%s",
        payload.get("order_id"),
        payload.get("user_id"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "payment_captured",
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        total_amount=payload.get("total_amount", ""),
        currency=payload.get("currency", ""),
        shop_name=_shop_name(),
    )

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_PAYMENT_CAPTURED,
        payload=payload,
    )


@outbox_handler(EVENT_PAYMENT_REJECTED)
async def on_payment_rejected_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send 'Paiement échoué' HTML email to the customer."""
    logger.info(
        "Payment rejected (customer email): order_id=%s user_id=%s reason=%s",
        payload.get("order_id"),
        payload.get("user_id"),
        payload.get("reason"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "payment_rejected",
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        reason=payload.get("reason") or "",
        shop_name=_shop_name(),
    )

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_PAYMENT_REJECTED,
        payload=payload,
    )


@outbox_handler(EVENT_PAYMENT_REFUNDED)
async def on_payment_refunded_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Send a 'Remboursement effectué' email to the customer."""
    logger.info(
        "Payment refunded (customer email): order_id=%s user_id=%s amount=%s",
        payload.get("order_id"),
        payload.get("user_id"),
        payload.get("amount"),
    )

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""

    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "payment_refunded",
        full_name=full_name or "client",
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        amount=payload.get("amount", ""),
        currency=payload.get("currency", ""),
        reason=payload.get("reason") or "",
        fully_refunded=bool(payload.get("fully_refunded")),
        shop_name=_shop_name(),
    )

    await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_PAYMENT_REFUNDED,
        payload=payload,
    )


@outbox_handler(EVENT_INVOICE_ISSUED)
async def on_invoice_issued_customer(
    session: AsyncSession, payload: dict[str, Any]
) -> None:
    """Deliver the issued invoice to the customer.

    The invoice was created and stored but never sent: the customer had to
    guess it existed and go and fetch it. The e-mail carries the numbers and a
    link to the account page rather than the PDF itself — rendering it needs
    WeasyPrint's system libraries, and a missing font must not cost the
    customer the notice that they have been invoiced.

    ``Invoice.emailed_at`` makes this idempotent: the outbox guarantees
    at-least-once delivery, so without it a replay would mail the same invoice
    again.
    """
    raw_invoice_id = payload.get("invoice_id")
    if not raw_invoice_id:
        logger.warning("invoice email: missing invoice_id in payload, skipping")
        return
    try:
        invoice_id = uuid.UUID(str(raw_invoice_id))
    except (TypeError, ValueError):
        logger.warning("invoice email: invalid invoice_id %r", raw_invoice_id)
        return

    invoice = await session.get(Invoice, invoice_id)
    if invoice is None:
        logger.warning("invoice email: invoice %s not found", invoice_id)
        return
    if invoice.emailed_at is not None:
        logger.info(
            "Invoice %s already e-mailed at %s — skipping replay",
            invoice.invoice_number,
            invoice.emailed_at,
        )
        return

    user = await _resolve_user_from_payload(session, payload)
    full_name = (user.full_name or user.email or "") if user else ""
    order_ref = await _resolve_order_ref(session, payload)

    email = render_email(
        "invoice_issued",
        full_name=full_name or "client",
        invoice_number=invoice.invoice_number,
        order_id=payload.get("order_id", ""),
        order_ref=order_ref,
        total_incl_tax=payload.get("total_incl_tax", ""),
        total_tax=payload.get("total_tax", ""),
        currency=payload.get("currency", ""),
        invoice_url=f"{settings.FRONTEND_HOST.rstrip('/')}/mon-compte",
        shop_name=_shop_name(),
    )

    delivered = await _send_order_email(
        session,
        user_id_raw=payload.get("user_id"),
        subject=email.subject,
        text=email.text,
        html=email.html,
        event_type=EVENT_INVOICE_ISSUED,
        payload=payload,
    )
    if not delivered:
        # Leave emailed_at unset so the ARQ retry tries again.
        raise RuntimeError(f"Invoice {invoice.invoice_number} e-mail was not delivered")

    invoice.emailed_at = datetime.now(timezone.utc)
    session.add(invoice)
    await session.commit()
