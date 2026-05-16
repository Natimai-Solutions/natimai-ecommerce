from app.features.notification.providers.base import (
    NotificationMessage,
    NotificationProvider,
    NotificationProviderError,
    NotificationResult,
    UnknownNotificationProviderError,
)
from app.features.notification.providers.mailgun import MailgunNotificationProvider
from app.features.notification.providers.noop import NoopNotificationProvider
from app.features.notification.providers.slack_webhook import (
    SlackWebhookNotificationProvider,
)

SUPPORTED_NOTIFICATION_PROVIDERS: dict[str, type[NotificationProvider]] = {
    NoopNotificationProvider.code: NoopNotificationProvider,
    MailgunNotificationProvider.code: MailgunNotificationProvider,
    SlackWebhookNotificationProvider.code: SlackWebhookNotificationProvider,
}


def get_notification_provider(provider_code: str) -> NotificationProvider:
    """Get notification provider."""
    normalized_code = provider_code.strip().lower()
    provider_class = SUPPORTED_NOTIFICATION_PROVIDERS.get(normalized_code)
    if provider_class is None:
        raise UnknownNotificationProviderError(normalized_code)

    return provider_class()


__all__ = [
    "MailgunNotificationProvider",
    "NoopNotificationProvider",
    "NotificationMessage",
    "NotificationProvider",
    "NotificationProviderError",
    "NotificationResult",
    "SUPPORTED_NOTIFICATION_PROVIDERS",
    "SlackWebhookNotificationProvider",
    "UnknownNotificationProviderError",
    "get_notification_provider",
]
