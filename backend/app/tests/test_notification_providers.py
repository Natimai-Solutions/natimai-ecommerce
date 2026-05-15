from __future__ import annotations

import pytest

from app.core.config import settings
from app.features.notification.providers import (
    SUPPORTED_NOTIFICATION_PROVIDERS,
    get_notification_provider,
)
from app.features.notification.providers.base import (
    NotificationMessage,
    UnknownNotificationProviderError,
)
from app.features.notification.providers.mailgun import MailgunNotificationProvider
from app.features.notification.providers.noop import NoopNotificationProvider
from app.features.notification.providers.slack_webhook import (
    SlackWebhookNotificationProvider,
)


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


def test_supported_notification_providers_contains_mailgun_noop_slack() -> None:
    assert "mailgun" in SUPPORTED_NOTIFICATION_PROVIDERS
    assert "noop" in SUPPORTED_NOTIFICATION_PROVIDERS
    assert "slack_webhook" in SUPPORTED_NOTIFICATION_PROVIDERS


def test_get_notification_provider_returns_mailgun_instance() -> None:
    provider = get_notification_provider("  MailGun ")

    assert isinstance(provider, MailgunNotificationProvider)


def test_get_notification_provider_returns_noop_instance() -> None:
    provider = get_notification_provider("noop")

    assert isinstance(provider, NoopNotificationProvider)


def test_get_notification_provider_returns_slack_instance() -> None:
    provider = get_notification_provider("slack_webhook")

    assert isinstance(provider, SlackWebhookNotificationProvider)


def test_get_notification_provider_unknown_raises() -> None:
    with pytest.raises(UnknownNotificationProviderError):
        get_notification_provider("smtp_custom")


@pytest.mark.anyio
async def test_noop_provider_send_always_delivers() -> None:
    provider = NoopNotificationProvider()

    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient="user_1",
            subject="hello",
            text="payload",
        )
    )

    assert result.delivered is True
    assert result.provider_code == "noop"


@pytest.mark.anyio
async def test_mailgun_provider_returns_error_when_not_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MAILGUN_API_KEY", None)
    monkeypatch.setattr(settings, "MAILGUN_DOMAIN", None)
    monkeypatch.setattr(settings, "MAILGUN_FROM_EMAIL", None)
    monkeypatch.setattr(settings, "EMAILS_FROM_EMAIL", None)

    provider = MailgunNotificationProvider()
    result = await provider.send(
        NotificationMessage(
            channel="email",
            recipient="customer@example.com",
            subject="Payment",
            text="Payment captured",
        )
    )

    assert result.delivered is False
    assert result.provider_code == "mailgun"
    assert result.error is not None


@pytest.mark.anyio
async def test_slack_provider_returns_error_when_webhook_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL", None)

    provider = SlackWebhookNotificationProvider()
    result = await provider.send(
        NotificationMessage(
            channel="slack",
            recipient="payment-alerts",
            subject="Payment",
            text="Payment rejected",
        )
    )

    assert result.delivered is False
    assert result.provider_code == "slack_webhook"
    assert result.error is not None
