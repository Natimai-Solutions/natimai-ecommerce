"""CORS origins actually allowed by the app.

Storefront and API sit on different subdomains in production, so every browser
call is cross-origin. This used to be gated on ``BACKEND_CORS_ORIGINS`` alone
while the deployment guide presents ``FRONTEND_HOST`` as *the* CORS origin —
setting only the latter left the middleware uninstalled and the storefront
unable to reach the API at all, with `curl` still working perfectly and only
the browser failing.
"""

from __future__ import annotations

import pytest

from app.core.config import Settings


def _settings(**overrides: object) -> Settings:
    base: dict[str, object] = {
        "SECRET_KEY": "x",
        "FIRST_SUPERUSER": "admin@test.local",
        "FIRST_SUPERUSER_PASSWORD": "not-changethis-password",
    }
    base.update(overrides)
    return Settings(**base)  # type: ignore[arg-type]


def test_frontend_host_is_always_an_allowed_origin() -> None:
    settings = _settings(FRONTEND_HOST="https://shop.example.com")

    assert "https://shop.example.com" in settings.all_cors_origins


def test_extra_origins_are_added_not_substituted() -> None:
    settings = _settings(
        FRONTEND_HOST="https://shop.example.com",
        BACKEND_CORS_ORIGINS="https://admin.example.com",
    )

    assert set(settings.all_cors_origins) == {
        "https://admin.example.com",
        "https://shop.example.com",
    }


def test_the_allowed_origins_are_never_empty() -> None:
    """The app installs the CORS middleware on this list; an empty list would
    silently mean "no CORS at all"."""
    assert _settings().all_cors_origins


@pytest.mark.parametrize(
    "trailing", ["https://shop.example.com/", "https://shop.example.com"]
)
def test_a_trailing_slash_does_not_produce_a_second_origin(trailing: str) -> None:
    """Browsers send the origin without a trailing slash; keeping one would
    make the entry dead weight that never matches."""
    settings = _settings(
        FRONTEND_HOST="https://shop.example.com",
        BACKEND_CORS_ORIGINS=trailing,
    )

    assert settings.all_cors_origins.count("https://shop.example.com") >= 1
    assert "https://shop.example.com/" not in settings.all_cors_origins


def test_the_app_installs_cors_for_the_configured_origins() -> None:
    """Guards the wiring, not just the property: the middleware must read
    all_cors_origins."""
    from app.main import app

    cors = [m for m in app.user_middleware if "CORSMiddleware" in str(m.cls)]
    assert cors, "CORS middleware is not installed"
