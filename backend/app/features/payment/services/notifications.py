from __future__ import annotations

import logging
from typing import Any

import httpx

from app.core.config import settings
from app.utils.email import send_email

logger = logging.getLogger(__name__)


def _as_non_empty_str(value: object | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _build_notification_message(event_type: str, payload: dict[str, Any]) -> str:
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


def _collect_email_targets(payload: dict[str, Any]) -> list[str]:
    targets: list[str] = []

    for key in ("user_id", "admin_user_id"):
        value = _as_non_empty_str(payload.get(key))
        if value and value not in targets:
            targets.append(value)

    support_email = _as_non_empty_str(settings.EMAIL_SUPPORT)
    if support_email and support_email not in targets:
        targets.append(support_email)

    return targets


async def _send_email_notifications(message: str, payload: dict[str, Any]) -> None:
    if not settings.PAYMENT_NOTIFICATIONS_EMAIL_ENABLED:
        return

    for target in _collect_email_targets(payload):
        try:
            await send_email(target, message)
        except Exception as exc:
            logger.warning(
                "Payment notification email failed for target=%s: %s",
                target,
                exc,
            )


async def _send_slack_notification(
    event_type: str,
    message: str,
    payload: dict[str, Any],
) -> None:
    if not settings.PAYMENT_NOTIFICATIONS_SLACK_ENABLED:
        return

    webhook_url = settings.PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL
    if webhook_url is None:
        logger.debug(
            "Slack notifications enabled but webhook URL is missing for payment event"
        )
        return

    body = {
        "text": message,
        "event_type": event_type,
        "payment_id": payload.get("payment_id"),
        "order_id": payload.get("order_id"),
        "provider_code": payload.get("provider_code"),
        "payload": payload,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(str(webhook_url), json=body)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Slack payment notification failed: %s", exc)


async def send_payment_event_notifications(
    *,
    event_type: str,
    payload: dict[str, Any],
) -> None:
    message = _build_notification_message(event_type, payload)

    await _send_email_notifications(message, payload)
    await _send_slack_notification(event_type, message, payload)
