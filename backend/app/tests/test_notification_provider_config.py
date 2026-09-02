"""A misspelt e-mail provider must not be discovered by its silence.

``PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER`` was a free string, and an unknown
value fell back to the "noop" provider at the first send — which reports
success and throws the message away. A typo in the .env therefore discarded
every order confirmation, every payment receipt and every invoice, with
nothing but a warning buried in the logs.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.config import Settings
from app.features.notification.providers import SUPPORTED_NOTIFICATION_PROVIDERS

_VALID_BASE: dict[str, object] = {
    "SECRET_KEY": "unit-test-secret-key-not-changethis",
    "POSTGRES_PASSWORD": "unit-test-password",
    "POSTGRES_DB": "unit_test_db",
    "FIRST_SUPERUSER": "ops@unit.test",
    "FIRST_SUPERUSER_PASSWORD": "unit-test-admin-password",
    "CLAMAV_ENABLED": True,
}


@pytest.mark.parametrize("provider", sorted(SUPPORTED_NOTIFICATION_PROVIDERS))
def test_every_supported_provider_is_accepted(provider: str) -> None:
    settings = Settings(
        ENVIRONMENT="production",
        PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER=provider,
        **_VALID_BASE,
    )
    assert settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER == provider


@pytest.mark.parametrize("typo", ["mailgnu", "Mailgun ", "sendgrid", ""])
def test_an_unknown_provider_fails_at_startup(typo: str) -> None:
    with pytest.raises(ValidationError, match="PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER"):
        Settings(
            ENVIRONMENT="production",
            PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER=typo,
            **_VALID_BASE,
        )


def test_the_accepted_values_match_the_provider_registry() -> None:
    """The literal is hand-maintained; this is what catches it drifting."""
    annotation = Settings.model_fields[
        "PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER"
    ].annotation
    accepted = set(getattr(annotation, "__args__", ()))
    assert accepted == set(SUPPORTED_NOTIFICATION_PROVIDERS)
