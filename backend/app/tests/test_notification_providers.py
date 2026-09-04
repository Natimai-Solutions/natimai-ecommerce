from __future__ import annotations

from typing import Any

import httpx
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
async def test_mailgun_provider_accepts_non_prefixed_api_key_format(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MAILGUN_API_KEY", "token-without-key-prefix")
    monkeypatch.setattr(settings, "MAILGUN_DOMAIN", "mg.example.com")
    monkeypatch.setattr(settings, "MAILGUN_FROM_EMAIL", "sender@example.com")
    monkeypatch.setattr(settings, "EMAILS_FROM_EMAIL", None)

    provider = MailgunNotificationProvider()
    assert provider._configuration_error() is None


@pytest.mark.anyio
async def test_mailgun_provider_accepts_display_name_from_email(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "MAILGUN_API_KEY", "key-invalid-but-shaped")
    monkeypatch.setattr(settings, "MAILGUN_DOMAIN", "mg.example.com")
    monkeypatch.setattr(
        settings,
        "MAILGUN_FROM_EMAIL",
        "Natimai Solutions <sender@example.com>",
    )
    monkeypatch.setattr(settings, "MAILGUN_FROM_NAME", None)

    provider = MailgunNotificationProvider()
    from_value = provider._build_from()

    assert from_value == "Natimai Solutions <sender@example.com>"


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


class _SlackClient:
    """httpx.AsyncClient factice : ``post`` renvoie la réponse préparée."""

    response: Any = None
    calls: list[dict[str, Any]] = []

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        _ = (args, kwargs)

    async def __aenter__(self) -> _SlackClient:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    async def post(self, url: str, **kwargs: Any) -> Any:
        _SlackClient.calls.append({"url": url, **kwargs})
        if isinstance(_SlackClient.response, Exception):
            raise _SlackClient.response
        return _SlackClient.response


@pytest.mark.anyio
async def test_slack_provider_posts_the_message_and_reports_delivery(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        settings,
        "PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL",
        "https://hooks.slack.test/services/x",
    )
    _SlackClient.calls = []
    _SlackClient.response = httpx.Response(
        200, request=httpx.Request("POST", "https://hooks.slack.test/services/x")
    )
    monkeypatch.setattr(
        "app.features.notification.providers.slack_webhook.httpx.AsyncClient",
        _SlackClient,
    )

    result = await SlackWebhookNotificationProvider().send(
        NotificationMessage(
            channel="slack",
            recipient="payment-alerts",
            subject="Paiement",
            text="Paiement refusé",
            metadata={"event_type": "payment.rejected"},
        )
    )

    assert result.delivered is True
    assert result.error is None
    body = _SlackClient.calls[0]["json"]
    assert body["text"] == "Paiement refusé"
    assert body["metadata"] == {"event_type": "payment.rejected"}


@pytest.mark.anyio
async def test_slack_provider_never_raises_on_transport_or_http_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Une alerte qui échoue ne doit jamais faire tomber le flux qui l'émet."""
    monkeypatch.setattr(
        settings,
        "PAYMENT_NOTIFICATIONS_SLACK_WEBHOOK_URL",
        "https://hooks.slack.test/services/x",
    )
    monkeypatch.setattr(
        "app.features.notification.providers.slack_webhook.httpx.AsyncClient",
        _SlackClient,
    )
    provider = SlackWebhookNotificationProvider()
    message = NotificationMessage(
        channel="slack", recipient="payment-alerts", subject="x", text="y"
    )

    _SlackClient.response = httpx.Response(
        500, request=httpx.Request("POST", "https://hooks.slack.test/services/x")
    )
    failed = await provider.send(message)
    assert failed.delivered is False and failed.error

    _SlackClient.response = httpx.ConnectError("refused")
    down = await provider.send(message)
    assert down.delivered is False and "refused" in (down.error or "")
