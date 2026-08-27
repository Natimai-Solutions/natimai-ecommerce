from __future__ import annotations

import logging
import re
import uuid
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.notification.email_renderer import render_email
from app.features.notification.providers import (
    NotificationMessage,
    NotificationProvider,
    UnknownNotificationProviderError,
    get_notification_provider,
)
from app.features.user.models.user import User

logger = logging.getLogger(__name__)

_EMAIL_CHANNEL = "email"
_SLACK_CHANNEL = "slack"

# Human-readable French labels for the admin notification (falls back to the
# raw technical event_type when an event is not listed here).
_EVENT_LABELS = {
    "payment.authorized": "Paiement autorisé",
    "payment.captured": "Paiement validé",
    "payment.completed": "Paiement validé",
    "payment.rejected": "Paiement refusé",
    "payment.failed": "Paiement échoué",
    "payment.refunded": "Remboursement effectué",
    "payment.cancelled": "Paiement annulé",
    "payment.amount_mismatch": "⚠ Montant encaissé incohérent — action requise",
}

# EmailStr validates user emails at write time, but payload values (UUIDs) and
# settings (EMAIL_SUPPORT) still pass through this guard so a malformed value
# never reaches the provider as a raw identifier.
_EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _as_non_empty_str(value: object | None) -> str | None:
    """Execute as non empty str."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _looks_like_email(value: str) -> bool:
    """Lightweight shape check on a candidate recipient address."""
    return bool(_EMAIL_PATTERN.match(value))


def _build_notification_message(event_type: str, payload: dict[str, Any]) -> str:
    """Build notification message."""
    payment_id = _as_non_empty_str(payload.get("payment_id")) or "unknown"
    order_id = _as_non_empty_str(payload.get("order_id")) or "n/a"
    provider_code = _as_non_empty_str(payload.get("provider_code")) or "unknown"
    reference = _as_non_empty_str(payload.get("provider_reference"))
    reason = _as_non_empty_str(payload.get("reason"))

    fragments = [
        f"event={event_type}",
        f"payment_id={payment_id}",
        f"order_id={order_id}",
        f"provider={provider_code}",
    ]
    if reference:
        fragments.append(f"reference={reference}")
    if reason:
        fragments.append(f"reason={reason}")

    return "Payment event: " + " ".join(fragments)


def _build_notification_subject(event_type: str, payload: dict[str, Any]) -> str:
    """Build notification subject."""
    payment_id = _as_non_empty_str(payload.get("payment_id")) or "unknown"
    return f"[Payment] {event_type} - {payment_id}"


def _build_admin_email_context(
    event_type: str, payload: dict[str, Any]
) -> dict[str, Any]:
    """Context for the admin_payment_event email template (shared visual style)."""
    return {
        "event_type": event_type,
        "event_label": _EVENT_LABELS.get(event_type, event_type),
        "payment_id": _as_non_empty_str(payload.get("payment_id")) or "—",
        "order_id": _as_non_empty_str(payload.get("order_id")) or "—",
        "provider_code": _as_non_empty_str(payload.get("provider_code")) or "—",
        "amount": _as_non_empty_str(payload.get("amount")) or "",
        "currency": _as_non_empty_str(payload.get("currency")) or "",
        "reference": _as_non_empty_str(payload.get("provider_reference")) or "",
        "reason": _as_non_empty_str(payload.get("reason")) or "",
        "shop_name": getattr(settings, "SHOP_NAME", "Natimai"),
    }


async def _resolve_user_email(
    session: AsyncSession,
    raw_user_id: object | None,
) -> str | None:
    """Resolve a payload user reference (UUID-as-string) to the user's email.

    Returns None when the value is absent, malformed, the user does not exist,
    or the user has no usable email recorded.
    """
    raw_str = _as_non_empty_str(raw_user_id)
    if raw_str is None:
        return None

    if _looks_like_email(raw_str):
        return raw_str

    try:
        user_uuid = uuid.UUID(raw_str)
    except (TypeError, ValueError):
        logger.debug(
            "Payment notification: skipping non-UUID user reference %r", raw_str
        )
        return None

    user = await session.get(User, user_uuid)
    if user is None:
        logger.warning(
            "Payment notification: user %s not found, cannot resolve email",
            user_uuid,
        )
        return None

    email = _as_non_empty_str(getattr(user, "email", None))
    if email is None or not _looks_like_email(email):
        logger.warning("Payment notification: user %s has no usable email", user_uuid)
        return None

    return email


async def _collect_email_targets(
    session: AsyncSession,
    payload: dict[str, Any],
) -> list[str]:
    """Execute collect email targets."""
    targets: list[str] = []

    # user_id is intentionally excluded: customer-facing payment emails
    # are sent by app.handlers.order (on_payment_captured / on_payment_rejected)
    # so that they can use proper Jinja2 HTML templates.
    for key in ("admin_user_id",):
        email = await _resolve_user_email(session, payload.get(key))
        if email and email not in targets:
            targets.append(email)

    support_email = _as_non_empty_str(settings.EMAIL_SUPPORT)
    if (
        support_email
        and _looks_like_email(support_email)
        and support_email not in targets
    ):
        targets.append(support_email)

    return targets


def _resolve_provider(provider_code: str) -> NotificationProvider:
    """Execute resolve provider."""
    try:
        return get_notification_provider(provider_code)
    except UnknownNotificationProviderError:
        logger.warning(
            "Unknown notification provider '%s', fallback to noop",
            provider_code,
        )
        return get_notification_provider("noop")


async def _send_email_notifications(
    session: AsyncSession,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Execute send email notifications."""
    if not settings.PAYMENT_NOTIFICATIONS_EMAIL_ENABLED:
        return

    targets = await _collect_email_targets(session, payload)
    if not targets:
        logger.info(
            "Payment notification %s: no resolvable email targets for payment_id=%s",
            event_type,
            payload.get("payment_id"),
        )
        return

    provider = _resolve_provider(settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER)
    # Same styled HTML shell as the customer-facing emails.
    email = render_email(
        "admin_payment_event", **_build_admin_email_context(event_type, payload)
    )

    for target in targets:
        result = await provider.send(
            NotificationMessage(
                channel=_EMAIL_CHANNEL,
                recipient=target,
                subject=email.subject,
                text=email.text,
                html=email.html,
                metadata={"event_type": event_type, "payload": payload},
            )
        )
        if not result.delivered:
            logger.warning(
                "Payment notification email failed for target=%s provider=%s: %s",
                target,
                result.provider_code,
                result.error,
            )


async def _send_slack_notification(
    event_type: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    """Execute send slack notification."""
    if not settings.PAYMENT_NOTIFICATIONS_SLACK_ENABLED:
        return

    provider = _resolve_provider(settings.PAYMENT_NOTIFICATIONS_SLACK_PROVIDER)
    result = await provider.send(
        NotificationMessage(
            channel=_SLACK_CHANNEL,
            recipient="payment-alerts",
            subject=_build_notification_subject(event_type, payload),
            text=message,
            metadata={"event_type": event_type, "payload": payload},
        )
    )
    if not result.delivered:
        logger.warning(
            "Slack payment notification failed with provider=%s: %s",
            result.provider_code,
            result.error,
        )


async def send_payment_event_notifications(
    *,
    session: AsyncSession,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Execute send payment event notifications."""
    # Slack keeps the compact key=value line; email uses the styled HTML template.
    message = _build_notification_message(event_type, payload)

    await _send_email_notifications(session, event_type, payload)
    await _send_slack_notification(event_type, message, payload)
