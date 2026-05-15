from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


class NotificationProviderError(Exception):
    """Base exception for notification provider failures."""


class UnknownNotificationProviderError(NotificationProviderError):
    """Raised when the provider registry receives an unknown provider code."""

    def __init__(self, provider_code: str) -> None:
        self.provider_code = provider_code
        super().__init__(f"Unknown notification provider: {provider_code}")


@dataclass(slots=True)
class NotificationMessage:
    channel: str
    recipient: str
    text: str
    subject: str | None = None
    metadata: dict[str, Any] | None = None


@dataclass(slots=True)
class NotificationResult:
    provider_code: str
    delivered: bool
    external_id: str | None = None
    error: str | None = None


class NotificationProvider(ABC):
    code: str

    @abstractmethod
    async def send(self, message: NotificationMessage) -> NotificationResult: ...
