from __future__ import annotations

import httpx

from app.core.config import settings
from app.features.notification.providers.base import (
    NotificationMessage,
    NotificationProvider,
    NotificationResult,
)


class SlackWebhookNotificationProvider(NotificationProvider):
    code = "slack_webhook"

    async def send(self, message: NotificationMessage) -> NotificationResult:
        webhook_url = settings.PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL
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

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(str(webhook_url), json=body)
            response.raise_for_status()
            return NotificationResult(provider_code=self.code, delivered=True)
        except Exception as exc:
            return NotificationResult(
                provider_code=self.code,
                delivered=False,
                error=str(exc),
            )
