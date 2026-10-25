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
        "app.features.notification.mailer.get_notification_provider",
        lambda _provider_code: _FakeProvider(),
    )

    admin_id = uuid.uuid4()
    admin = _user("admin@example.com", uid=admin_id)

    session = AsyncMock()
    session.get = AsyncMock(return_value=admin)

    await send_payment_event_notifications(
        session=session,
        event_type="payment.captured",
        payload={
            "payment_id": "pay_1",
            "order_id": "ord_1",
            "provider_code": "payzen",
            "user_id": str(uuid.uuid4()),
            "admin_user_id": str(admin_id),
        },
    )

    # user_id is intentionally ignored by technical notifications.
    assert sent_recipients == ["admin@example.com"]


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
        "app.features.notification.mailer.get_notification_provider",
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
async def test_an_unknown_email_provider_is_a_failed_send_not_a_silent_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The mailer no longer falls back to noop, which declared success and
    threw the message away: an unknown provider is a failure, journaled."""
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER", "custom")
    monkeypatch.setattr(settings, "EMAIL_SUPPORT", None)

    provider_calls: list[str] = []

    def _fake_get_provider(provider_code: str) -> Any:
        provider_calls.append(provider_code)
        raise UnknownNotificationProviderError(provider_code)

    monkeypatch.setattr(
        "app.features.notification.mailer.get_notification_provider",
        _fake_get_provider,
    )
    sent: list[Any] = []

    async def _deliver_spy(log: Any, **kwargs: Any) -> Any:
        result = await real_deliver(log, **kwargs)
        sent.append(log)
        return result

    from app.features.notification import mailer

    real_deliver = mailer.deliver
    monkeypatch.setattr(mailer, "deliver", _deliver_spy)

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
            "admin_user_id": str(customer_id),
        },
    )

    assert provider_calls == ["custom"]
    assert [log.status for log in sent] == ["failed"]
