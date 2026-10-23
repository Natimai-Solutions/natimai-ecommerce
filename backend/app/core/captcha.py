"""Cloudflare Turnstile on the public forms (R8 / U5).

Sign-up code, stock alert of a visitor, guest quote: the forms anyone can
submit without an account. When the back-office stores a Turnstile site key
and secret (Paramètres → Sécurité), the storefront renders the widget and
sends its token in the ``X-Captcha-Token`` header; the API verifies it with
Cloudflare before doing anything. Without a secret, nothing changes: the
check is a no-op, so a shop can start without a captcha.

Fail-open on a Cloudflare outage (logged): a down verification service must
not take the sign-up down with it. The rate limits still apply — they fail
closed (``core/rate_limit``), so the outage never leaves a form unguarded.
"""

from __future__ import annotations

import logging
from typing import Any

import httpx
from fastapi import Request

from app.core.errors import AppError
from app.core.rate_limit import get_client_ip

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TOKEN_HEADER = "X-Captcha-Token"
SITE_KEY_SETTING = "captcha_turnstile_site_key"
SECRET_SETTING = "captcha_turnstile_secret"  # noqa: S105 - a setting name


async def captcha_secret(session: Any) -> str:
    from app.core import runtime_settings

    return str(await runtime_settings.get(SECRET_SETTING, session) or "").strip()


async def captcha_site_key(session: Any) -> str:
    from app.core import runtime_settings

    return str(await runtime_settings.get(SITE_KEY_SETTING, session) or "").strip()


async def verify_token(secret: str, token: str, remote_ip: str | None) -> bool | None:
    """Ask Cloudflare; ``None`` when the verification service did not answer."""
    data = {"secret": secret, "response": token}
    if remote_ip and remote_ip != "unknown":
        data["remoteip"] = remote_ip
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(VERIFY_URL, data=data)
            response.raise_for_status()
            payload = response.json()
    except Exception:  # noqa: BLE001 - the outage is logged, not propagated
        logger.warning("Turnstile verification unavailable", exc_info=True)
        return None
    return bool(payload.get("success"))


async def require_captcha(request: Request, session: Any) -> None:
    """Enforce the captcha on a public form when the shop configured one.

    Raises ``captcha.required`` (400) without a token, ``captcha.failed``
    (400) when Cloudflare refuses it.
    """
    secret = await captcha_secret(session)
    if not secret:
        return
    token = (request.headers.get(TOKEN_HEADER) or "").strip()
    if not token:
        raise AppError(
            code="captcha.required",
            status_code=400,
            message="Vérification anti-robot requise",
            details={"header": TOKEN_HEADER},
        )
    verdict = await verify_token(secret, token, get_client_ip(request))
    if verdict is False:
        raise AppError(
            code="captcha.failed",
            status_code=400,
            message="Vérification anti-robot échouée : réessayez",
            details={"header": TOKEN_HEADER},
        )


__all__ = [
    "SECRET_SETTING",
    "SITE_KEY_SETTING",
    "TOKEN_HEADER",
    "VERIFY_URL",
    "captcha_secret",
    "captcha_site_key",
    "require_captcha",
    "verify_token",
]
