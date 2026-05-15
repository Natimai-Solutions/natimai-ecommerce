from __future__ import annotations

from typing import Any

import pytest

from app.core.config import settings
from app.features.notification.providers.base import (
    NotificationResult,
    UnknownNotificationProviderError,
)
from app.features.payment.services.notifications import send_payment_event_notifications


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.mark.anyio
async def test_send_payment_event_notifications_uses_configured_email_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_SLACK_ENABLED", False)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER", "mailgun")

    sent_recipients: list[str] = []

    class _FakeProvider:
        async def send(self, message: Any) -> NotificationResult:
            sent_recipients.append(message.recipient)
            return NotificationResult(provider_code="mailgun", delivered=True)

    monkeypatch.setattr(
        "app.features.payment.services.notifications.get_notification_provider",
        lambda _provider_code: _FakeProvider(),
    )

    await send_payment_event_notifications(
        event_type="payment.captured",
        payload={
            "payment_id": "pay_1",
            "order_id": "ord_1",
            "provider_code": "payzen",
            "user_id": "user_1",
            "admin_user_id": "admin_1",
        },
    )

    assert sorted(sent_recipients) == ["admin_1", "user_1"]


@pytest.mark.anyio
async def test_send_payment_event_notifications_fallbacks_to_noop_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_SLACK_ENABLED", False)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER", "custom")

    provider_calls: list[str] = []
    delivered_by_provider: list[str] = []

    class _FakeNoopProvider:
        async def send(self, _message: Any) -> NotificationResult:
            delivered_by_provider.append("noop")
            return NotificationResult(provider_code="noop", delivered=True)

    def _fake_get_provider(provider_code: str) -> Any:
        provider_calls.append(provider_code)
        if provider_code == "custom":
            raise UnknownNotificationProviderError(provider_code)
        if provider_code == "noop":
            return _FakeNoopProvider()
        raise AssertionError(f"Unexpected provider: {provider_code}")

    monkeypatch.setattr(
        "app.features.payment.services.notifications.get_notification_provider",
        _fake_get_provider,
    )

    await send_payment_event_notifications(
        event_type="payment.rejected",
        payload={
            "payment_id": "pay_2",
            "order_id": "ord_2",
            "provider_code": "payzen",
            "user_id": "user_2",
        },
    )

    assert provider_calls[:2] == ["custom", "noop"]
    assert delivered_by_provider == ["noop"]
