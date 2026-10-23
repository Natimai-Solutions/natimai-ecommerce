from __future__ import annotations

import logging

from app.core.logging_config import mask_email
from app.features.notification.providers.base import (
    NotificationMessage,
    NotificationProvider,
    NotificationResult,
)

logger = logging.getLogger(__name__)


class NoopNotificationProvider(NotificationProvider):
    """Represents noop notification provider."""

    code = "noop"

    async def send(self, message: NotificationMessage) -> NotificationResult:
        """Execute send."""
        logger.info(
            "Noop notification provider: channel=%s recipient=%s subject=%s",
            message.channel,
            mask_email(message.recipient),
            message.subject,
        )
        return NotificationResult(
            provider_code=self.code,
            delivered=True,
            external_id="noop",
        )
