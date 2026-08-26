"""Startup guards of ``app.core.config.Settings`` (S3 audit fix).

CLAMAV_ENABLED=False falls back to the NoOpScanner (every upload declared
clean): tolerated with a warning in local development, refused elsewhere.
"""

from types import SimpleNamespace
from typing import Any, cast

import pytest

from app.core.config import Settings


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
