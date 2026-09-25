"""Generic outbound JSON webhook (Make, Zapier, Buffer, IFTTT, Slack…).

``post_json`` never raises: the callers (reminders, alerts) record the failure
and move on. Only https URLs are accepted.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=15, connect=5)


async def post_json(url: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
    """POST ``payload`` to ``url``. Returns ``(delivered, error)``."""
    if not url.lower().startswith("https://"):
        return False, "URL non sécurisée (https requis)"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(url, json=payload) as response:
                if response.status >= 400:
                    body = (await response.text())[:200]
                    return False, f"HTTP {response.status}: {body}"
                return True, None
    except Exception as exc:  # noqa: BLE001 — a dead webhook must not raise
        logger.warning("Webhook %s unreachable: %s", url, exc)
        return False, str(exc)[:500]
