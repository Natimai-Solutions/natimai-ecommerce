"""Startup guards of ``app.core.config.Settings`` (S3/S4 audit fixes).

CLAMAV_ENABLED=False falls back to the NoOpScanner (every upload declared
clean) and an empty SECRET_KEY would silently rotate every JWT at each
restart: both are tolerated with a warning in local development and refused
elsewhere.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.core.config import Settings

# Values that satisfy every *other* startup guard, so a failure below can only
# come from the ClamAV one.
_VALID_BASE_SETTINGS: dict[str, Any] = {
    "SECRET_KEY": "unit-test-secret-key-not-changethis",
    "POSTGRES_PASSWORD": "unit-test-password",
    "POSTGRES_DB": "unit_test_db",
    "FIRST_SUPERUSER": "ops@unit.test",
    "FIRST_SUPERUSER_PASSWORD": "unit-test-admin-password",
}


def test_secret_key_empty_raises_outside_local() -> None:
    for env in ("staging", "production"):
        fake: Any = SimpleNamespace(SECRET_KEY="", ENVIRONMENT=env)
        with pytest.raises(ValueError, match="SECRET_KEY"):
            Settings._check_secret_key(cast(Settings, fake))


def test_secret_key_empty_generates_with_warning_in_local() -> None:
    fake: Any = SimpleNamespace(SECRET_KEY="", ENVIRONMENT="local")
    with pytest.warns(UserWarning, match="SECRET_KEY"):
        Settings._check_secret_key(cast(Settings, fake))
    assert fake.SECRET_KEY


def test_secret_key_set_passes_everywhere() -> None:
    for env in ("local", "staging", "production"):
        fake: Any = SimpleNamespace(SECRET_KEY="a-real-secret", ENVIRONMENT=env)
        Settings._check_secret_key(cast(Settings, fake))
        assert fake.SECRET_KEY == "a-real-secret"


def _fake_settings(environment: str, *, clamav_enabled: bool) -> Any:
    return SimpleNamespace(ENVIRONMENT=environment, CLAMAV_ENABLED=clamav_enabled)


def test_clamav_disabled_raises_outside_local() -> None:
    for env in ("staging", "production"):
        fake = _fake_settings(env, clamav_enabled=False)
        with pytest.raises(ValueError, match="CLAMAV_ENABLED"):
            Settings._check_clamav_enabled(cast(Settings, fake))


def test_clamav_disabled_warns_in_local() -> None:
    fake = _fake_settings("local", clamav_enabled=False)
    with pytest.warns(UserWarning, match="CLAMAV_ENABLED"):
        Settings._check_clamav_enabled(cast(Settings, fake))


def test_clamav_enabled_passes_everywhere() -> None:
    for env in ("local", "staging", "production"):
        fake = _fake_settings(env, clamav_enabled=True)
        Settings._check_clamav_enabled(cast(Settings, fake))


# ── Full-model tests ──────────────────────────────────────────────────────────
# The three tests above call the guard in isolation, so they stay green even if
# `_enforce_non_default_secrets` stops calling it. These build a real Settings
# and therefore cover the wiring too.


def test_settings_refuses_to_build_without_clamav_in_production() -> None:
    with pytest.raises(ValueError, match="CLAMAV_ENABLED"):
        Settings(
            ENVIRONMENT="production",
            CLAMAV_ENABLED=False,
            **_VALID_BASE_SETTINGS,
        )


def test_settings_builds_with_clamav_in_production() -> None:
    settings = Settings(
        ENVIRONMENT="production",
        CLAMAV_ENABLED=True,
        **_VALID_BASE_SETTINGS,
    )

    assert settings.CLAMAV_ENABLED is True
    assert settings.ENVIRONMENT == "production"


def test_settings_only_warns_without_clamav_in_local() -> None:
    with pytest.warns(UserWarning, match="CLAMAV_ENABLED"):
        settings = Settings(
            ENVIRONMENT="local",
            CLAMAV_ENABLED=False,
            **_VALID_BASE_SETTINGS,
        )

    assert settings.CLAMAV_ENABLED is False


def _fake_db_password(environment: str, password: str) -> Any:
    return SimpleNamespace(ENVIRONMENT=environment, POSTGRES_PASSWORD=password)


def test_weak_database_password_raises_outside_local() -> None:
    """The compose default must never reach a deployed environment."""
    for env in ("staging", "production"):
        for password in ("postgres", "POSTGRES", " postgres ", "password"):
            fake = _fake_db_password(env, password)
            with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
                Settings._check_weak_database_password(cast(Settings, fake))


def test_weak_database_password_warns_in_local() -> None:
    """`docker compose up` with no .env stays usable, but says so."""
    fake = _fake_db_password("local", "postgres")
    with pytest.warns(UserWarning, match="POSTGRES_PASSWORD"):
        Settings._check_weak_database_password(cast(Settings, fake))


def test_real_database_password_passes_everywhere() -> None:
    for env in ("local", "staging", "production"):
        fake = _fake_db_password(env, "a-real-database-password")
        Settings._check_weak_database_password(cast(Settings, fake))


def test_settings_refuses_to_build_with_compose_default_password() -> None:
    base = {**_VALID_BASE_SETTINGS, "POSTGRES_PASSWORD": "postgres"}
    with pytest.raises(ValueError, match="POSTGRES_PASSWORD"):
        Settings(ENVIRONMENT="production", CLAMAV_ENABLED=True, **base)
