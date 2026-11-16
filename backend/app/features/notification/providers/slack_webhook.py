from __future__ import annotations

import httpx

from app.core.ssrf import public_only_transport
from app.core.webhook import allowed_webhook_url
from app.features.notification.providers.base import (
    NotificationMessage,
    NotificationProvider,
    NotificationResult,
)


class SlackWebhookNotificationProvider(NotificationProvider):
    """Represents slack webhook notification provider."""

    code = "slack_webhook"

    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Execute send."""
        from app.core import runtime_settings

        webhook_url = (
            await runtime_settings.get("notifications_slack_webhook_url") or None
        )
        if webhook_url is None:
            return NotificationResult(
                provider_code=self.code,
                delivered=False,
                error="PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL is not configured",
            )

        body = {
            "text": message.text,
            "channel": message.channel,
            "recipient": message.recipient,
            "subject": message.subject,
            "metadata": message.metadata,
        }

        # An address typed by an administrator: https to an allow-listed
        # host, public addresses only, no redirect — like the other outbound
        # webhook (audit 2026-11).
        target = allowed_webhook_url(str(webhook_url))
        if target is None:
            return NotificationResult(
                provider_code=self.code,
                delivered=False,
                error=(
                    "URL refusée : https vers un service autorisé uniquement "
                    "(OUTBOUND_WEBHOOK_ALLOWED_HOSTS)"
                ),
            )
        try:
            async with httpx.AsyncClient(
                timeout=10.0, transport=public_only_transport()
            ) as client:
                response = await client.post(target, json=body)
            response.raise_for_status()
            return NotificationResult(provider_code=self.code, delivered=True)
        except Exception as exc:
            return NotificationResult(
                provider_code=self.code,
                delivered=False,
                error=str(exc),
            )
