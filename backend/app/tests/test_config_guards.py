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
    # Production also requires S3 for the uploads (see the storage guard).
    "FILE_STORAGE_BACKEND": "s3",
    "S3_BUCKET_NAME": "unit-test-bucket",
    "S3_ACCESS_KEY_ID": "unit-test-key",
    "S3_SECRET_KEY_ID": "unit-test-secret",
    # Production requires the administrators' 2FA, hence its encryption key.
    "SECRETS_ENCRYPTION_KEY": "unit-test-fernet-key",
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
    key = "a-real-secret-of-thirty-two-chars-at-least"
    for env in ("local", "staging", "production"):
        fake: Any = SimpleNamespace(SECRET_KEY=key, ENVIRONMENT=env)
        Settings._check_secret_key(cast(Settings, fake))
        assert fake.SECRET_KEY == key


def test_short_secret_key_is_refused_outside_local_and_warned_in_local() -> None:
    """R8 / confort: a short key is cheap to brute-force."""
    for env in ("staging", "production"):
        fake: Any = SimpleNamespace(SECRET_KEY="too-short", ENVIRONMENT=env)
        with pytest.raises(ValueError, match="32"):
            Settings._check_secret_key(cast(Settings, fake))
    local: Any = SimpleNamespace(SECRET_KEY="too-short", ENVIRONMENT="local")
    with pytest.warns(UserWarning, match="32"):
        Settings._check_secret_key(cast(Settings, local))
    assert local.SECRET_KEY == "too-short"  # kept: the developer chose it


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


# -- file storage (R6) -------------------------------------------------------


def _storage(environment: str, backend: str, **extra: Any) -> Any:
    values: dict[str, Any] = {
        "ENVIRONMENT": environment,
        "FILE_STORAGE_BACKEND": backend,
        "FILE_STORAGE_ALLOW_LOCAL": False,
        "S3_BUCKET_NAME": None,
        "S3_ACCESS_KEY_ID": None,
        "S3_SECRET_KEY_ID": None,
    }
    values.update(extra)
    return SimpleNamespace(**values)


def test_local_storage_is_refused_in_production() -> None:
    with pytest.raises(ValueError, match="FILE_STORAGE_BACKEND"):
        Settings._check_file_storage(cast(Settings, _storage("production", "local")))


def test_local_storage_only_warns_in_staging_and_passes_in_local() -> None:
    with pytest.warns(UserWarning, match="FILE_STORAGE_BACKEND"):
        Settings._check_file_storage(cast(Settings, _storage("staging", "local")))
    Settings._check_file_storage(cast(Settings, _storage("local", "local")))


def test_a_deliberate_local_volume_is_allowed() -> None:
    fake = _storage("production", "local", FILE_STORAGE_ALLOW_LOCAL=True)
    Settings._check_file_storage(cast(Settings, fake))


def test_s3_needs_its_bucket_and_keys() -> None:
    with pytest.raises(ValueError, match="S3_BUCKET_NAME"):
        Settings._check_file_storage(
            cast(Settings, _storage("production", "s3", S3_ACCESS_KEY_ID="k"))
        )
    complete = _storage(
        "production",
        "s3",
        S3_BUCKET_NAME="b",
        S3_ACCESS_KEY_ID="k",
        S3_SECRET_KEY_ID="s",
    )
    Settings._check_file_storage(cast(Settings, complete))


# -- administrators' 2FA (R6) -------------------------------------------------


def test_required_2fa_needs_the_encryption_key() -> None:
    def fake(env: str, key: str | None, required: bool | None = None) -> Any:
        return SimpleNamespace(
            ENVIRONMENT=env,
            SECRETS_ENCRYPTION_KEY=key,
            admin_2fa_required=required
            if required is not None
            else env == "production",
        )

    with pytest.raises(ValueError, match="SECRETS_ENCRYPTION_KEY"):
        Settings._check_secrets_key_for_2fa(cast(Settings, fake("production", None)))
    Settings._check_secrets_key_for_2fa(cast(Settings, fake("production", "k")))
    # Not required (staging by default): nothing to check.
    Settings._check_secrets_key_for_2fa(cast(Settings, fake("staging", None)))
    with pytest.warns(UserWarning, match="SECRETS_ENCRYPTION_KEY"):
        Settings._check_secrets_key_for_2fa(
            cast(Settings, fake("local", None, required=True))
        )


def test_2fa_is_required_in_production_by_default() -> None:
    base = {**_VALID_BASE_SETTINGS, "CLAMAV_ENABLED": True}
    assert Settings(ENVIRONMENT="production", **base).admin_2fa_required is True
    assert Settings(ENVIRONMENT="staging", **base).admin_2fa_required is False
    forced = Settings(ENVIRONMENT="staging", ADMIN_2FA_REQUIRED=True, **base)
    assert forced.admin_2fa_required is True


# -- placeholders of .env.example (audit 2026-11, S1) -----------------------


@pytest.mark.parametrize(
    "variable",
    ["SECRET_KEY", "POSTGRES_PASSWORD", "FIRST_SUPERUSER_PASSWORD"],
)
@pytest.mark.parametrize(
    "placeholder",
    [
        "changethis",
        "changeme-generate-a-secure-random-key",
        "changeme-strong-database-password",
        "ChangeMe-strong-admin-password",
    ],
)
def test_settings_refuse_the_env_example_placeholders_in_production(
    variable: str, placeholder: str
) -> None:
    """A copied .env.example must not start in production: its SECRET_KEY is
    public (anyone could sign an admin JWT), and so are the passwords."""
    base = {**_VALID_BASE_SETTINGS, variable: placeholder}
    with pytest.raises(ValueError, match=variable):
        Settings(ENVIRONMENT="production", CLAMAV_ENABLED=True, **base)


def test_env_example_placeholders_only_warn_in_local() -> None:
    fake: Any = SimpleNamespace(ENVIRONMENT="local")
    with pytest.warns(UserWarning, match="SECRET_KEY"):
        Settings._check_default_secret(
            cast(Settings, fake), "SECRET_KEY", "changeme-generate-a-secure-key"
        )


def test_real_secrets_and_empty_values_are_not_placeholders() -> None:
    fake: Any = SimpleNamespace(ENVIRONMENT="production")
    for value in ("a-real-value-that-mentions-changeme-later", "", None):
        Settings._check_default_secret(cast(Settings, fake), "X", value)
