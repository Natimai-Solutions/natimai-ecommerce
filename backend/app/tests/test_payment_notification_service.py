from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

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


def _user(email: str, *, uid: uuid.UUID | None = None) -> Any:
    return SimpleNamespace(id=uid or uuid.uuid4(), email=email)


@pytest.mark.anyio
async def test_send_payment_event_notifications_uses_configured_email_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_SLACK_ENABLED", False)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER", "mailgun")
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", None)

    sent_recipients: list[str] = []

    class _FakeProvider:
        async def send(self, message: Any) -> NotificationResult:
            sent_recipients.append(message.recipient)
            return NotificationResult(provider_code="mailgun", delivered=True)

    monkeypatch.setattr(
        "app.features.payment.services.notifications.get_notification_provider",
        lambda _provider_code: _FakeProvider(),
    )

    customer_id = uuid.uuid4()
    admin_id = uuid.uuid4()
    customer = _user("customer@example.com", uid=customer_id)
    admin = _user("admin@example.com", uid=admin_id)

    session = AsyncMock()
    session.get = AsyncMock(side_effect=[customer, admin])

    await send_payment_event_notifications(
        session=session,
        event_type="payment.captured",
        payload={
            "payment_id": "pay_1",
            "order_id": "ord_1",
            "provider_code": "payzen",
            "user_id": str(customer_id),
            "admin_user_id": str(admin_id),
        },
    )

    assert sorted(sent_recipients) == ["admin@example.com", "customer@example.com"]


@pytest.mark.anyio
async def test_send_payment_event_notifications_skips_unresolvable_user(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A non-UUID or missing user reference must never reach the provider."""
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_SLACK_ENABLED", False)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER", "mailgun")
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", "support@example.com")

    sent_recipients: list[str] = []

    class _FakeProvider:
        async def send(self, message: Any) -> NotificationResult:
            sent_recipients.append(message.recipient)
            return NotificationResult(provider_code="mailgun", delivered=True)

    monkeypatch.setattr(
        "app.features.payment.services.notifications.get_notification_provider",
        lambda _provider_code: _FakeProvider(),
    )

    session = AsyncMock()
    session.get = AsyncMock(return_value=None)

    await send_payment_event_notifications(
        session=session,
        event_type="payment.captured",
        payload={
            "payment_id": "pay_1",
            "order_id": "ord_1",
            "provider_code": "payzen",
            "user_id": "not-a-uuid",
            "admin_user_id": str(uuid.uuid4()),
        },
    )

    # Only the support email reaches the provider; the malformed user_id is
    # discarded silently and the unknown admin user resolves to None.
    assert sent_recipients == ["support@example.com"]


@pytest.mark.anyio
async def test_send_payment_event_notifications_fallbacks_to_noop_provider(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_ENABLED", True)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_SLACK_ENABLED", False)
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER", "custom")
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", None)

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

    customer_id = uuid.uuid4()
    session = AsyncMock()
    session.get = AsyncMock(return_value=_user("user2@example.com", uid=customer_id))

    await send_payment_event_notifications(
        session=session,
        event_type="payment.rejected",
        payload={
            "payment_id": "pay_2",
            "order_id": "ord_2",
            "provider_code": "payzen",
            "user_id": str(customer_id),
        },
    )

    assert provider_calls[:2] == ["custom", "noop"]
    assert delivered_by_provider == ["noop"]
