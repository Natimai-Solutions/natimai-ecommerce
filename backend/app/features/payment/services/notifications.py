from __future__ import annotations

import logging
from typing import Any

from app.core.config import settings
from app.features.notification.providers import (
    NotificationMessage,
    NotificationProvider,
    UnknownNotificationProviderError,
    get_notification_provider,
)

logger = logging.getLogger(__name__)

_EMAIL_CHANNEL = "email"
_SLACK_CHANNEL = "slack"


def _as_non_empty_str(value: object | None) -> str | None:
    """Execute as non empty str."""
    if value is None:
        return None
    text = str(value).strip()
    return text or None


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


def _collect_email_targets(payload: dict[str, Any]) -> list[str]:
    """Execute collect email targets."""
    targets: list[str] = []

    for key in ("user_id", "admin_user_id"):
        value = _as_non_empty_str(payload.get(key))
        if value and value not in targets:
            targets.append(value)

    support_email = _as_non_empty_str(settings.EMAIL_SUPPORT)
    if support_email and support_email not in targets:
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
    event_type: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    """Execute send email notifications."""
    if not settings.PAYMENT_NOTIFICATIONS_EMAIL_ENABLED:
        return

    provider = _resolve_provider(settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER)
    subject = _build_notification_subject(event_type, payload)

    for target in _collect_email_targets(payload):
        result = await provider.send(
            NotificationMessage(
                channel=_EMAIL_CHANNEL,
                recipient=target,
                subject=subject,
                text=message,
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
    event_type: str,
    payload: dict[str, Any],
) -> None:
    """Execute send payment event notifications."""
    message = _build_notification_message(event_type, payload)

    await _send_email_notifications(event_type, message, payload)
    await _send_slack_notification(event_type, message, payload)
