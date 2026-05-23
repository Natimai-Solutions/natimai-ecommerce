from __future__ import annotations

from typing import Any

import httpx

from app.core.config import settings
from app.features.notification.providers.base import (
    NotificationMessage,
    NotificationProvider,
    NotificationResult,
)


class MailgunNotificationProvider(NotificationProvider):
    """Represents mailgun notification provider."""

    code = "mailgun"

    def _build_from(self) -> str | None:
        """Build from."""
        from_email = settings.MAILGUN_FROM_EMAIL or settings.EMAILS_FROM_EMAIL
        if not from_email:
            return None

        from_name = (
            settings.MAILGUN_FROM_NAME
            or settings.EMAILS_FROM_NAME
            or settings.PROJECT_NAME
        )
        return f"{from_name} <{from_email}>"

    def _configuration_error(self) -> str | None:
        """Execute configuration error."""
        if not settings.MAILGUN_API_KEY:
            return "MAILGUN_API_KEY is not configured"
        if not settings.MAILGUN_DOMAIN:
            return "MAILGUN_DOMAIN is not configured"
        if not self._build_from():
            return "MAILGUN_FROM_EMAIL/EMAILS_FROM_EMAIL is not configured"
        return None

    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Execute send."""
        error = self._configuration_error()
        if error is not None:
            return NotificationResult(
                provider_code=self.code,
                delivered=False,
                error=error,
            )

        from_value = self._build_from()
        if from_value is None:
            return NotificationResult(
                provider_code=self.code,
                delivered=False,
                error="Missing sender identity",
            )

        url = (
            f"{settings.MAILGUN_API_BASE_URL.rstrip('/')}/"
            f"{settings.MAILGUN_DOMAIN}/messages"
        )
        data = {
            "from": from_value,
            "to": [message.recipient],
            "subject": message.subject or "Notification",
            "text": message.text,
        }

        metadata: dict[str, Any] = message.metadata or {}
        event_type = metadata.get("event_type")
        if isinstance(event_type, str) and event_type.strip():
            data["o:tag"] = event_type.strip()

        try:
            async with httpx.AsyncClient(
                timeout=settings.MAILGUN_TIMEOUT_SECONDS
            ) as client:
                response = await client.post(
                    url,
                    auth=("api", settings.MAILGUN_API_KEY or ""),
                    data=data,
                )
            response.raise_for_status()

            external_id: str | None = None
            body = response.json() if response.content else None
            if isinstance(body, dict):
                raw_id = body.get("id")
                external_id = str(raw_id) if raw_id is not None else None

            return NotificationResult(
                provider_code=self.code,
                delivered=True,
                external_id=external_id,
            )
        except Exception as exc:
            return NotificationResult(
                provider_code=self.code,
                delivered=False,
                error=str(exc),
            )
