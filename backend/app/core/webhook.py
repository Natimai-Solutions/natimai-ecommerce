"""Generic outbound JSON webhook (Make, Zapier, Slack, IFTTT…).

``post_json`` never raises: the callers (reminders, alerts) record the failure
and move on. The URL is typed by an administrator, so three guards apply
(audit 2026-11):

* https only, to a host of ``OUTBOUND_WEBHOOK_ALLOWED_HOSTS`` — the request
  is rebuilt on the allow-list entry, never on the typed host;
* the connection reaches public addresses only, checked at connection time
  (``app/core/ssrf.py``: no DNS rebinding);
* no redirect followed.
"""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urlsplit

import aiohttp

from app.core.config import settings
from app.core.ssrf import public_only_connector

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5)


def allowed_webhook_url(url: str) -> str | None:
    """``url`` rebuilt on its allow-listed host, or None when refused."""
    parts = urlsplit(url.strip())
    if parts.scheme.lower() != "https" or parts.username or parts.password:
        return None
    if parts.port not in (None, 443):
        return None
    hostname = (parts.hostname or "").lower()
    allowed = [
        str(host).strip().lower()
        for host in settings.OUTBOUND_WEBHOOK_ALLOWED_HOSTS
        if str(host).strip()
    ]
    for host in allowed:
        if hostname == host:
            path = parts.path or "/"
            query = f"?{parts.query}" if parts.query else ""
            # The host part comes from the allow-list, not from the input.
            return f"https://{host}{path}{query}"
    return None


async def post_json(url: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
    """POST ``payload`` to ``url``. Returns ``(delivered, error)``."""
    target = allowed_webhook_url(url)
    if target is None:
        return False, (
            "URL refusée : https vers un service autorisé uniquement "
            "(OUTBOUND_WEBHOOK_ALLOWED_HOSTS)"
        )
    try:
        async with aiohttp.ClientSession(
            timeout=_TIMEOUT, connector=public_only_connector()
        ) as session:
            async with session.post(
                target, json=payload, allow_redirects=False
            ) as response:
                if 300 <= response.status < 400:
                    return False, f"HTTP {response.status}: redirection refusée"
                if response.status >= 400:
                    body = (await response.text())[:200]
                    return False, f"HTTP {response.status}: {body}"
                return True, None
    except Exception as exc:  # noqa: BLE001 — a dead webhook must not raise
        logger.warning("Webhook unreachable: %s", type(exc).__name__)
        return False, str(exc)[:500]
