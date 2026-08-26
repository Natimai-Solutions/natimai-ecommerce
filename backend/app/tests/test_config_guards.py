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
