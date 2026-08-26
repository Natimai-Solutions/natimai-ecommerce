"""Minimal webhook alerting.

Posts a JSON ``{"text": …}`` payload to ``ALERT_WEBHOOK_URL`` — the format of
Slack incoming webhooks, also accepted by Mattermost (for Discord, append
``/slack`` to the webhook URL). No-op when the variable is unset.

``send_alert`` never raises: an alerting failure must never take down the
caller (health checker, worker…).
"""

from __future__ import annotations

import logging

import aiohttp

from app.core.config import settings

logger = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=10, connect=5)


async def send_alert(message: str, *, source: str = "backend") -> bool:
    """Post an alert to the configured webhook. Returns True when delivered."""
    url = settings.ALERT_WEBHOOK_URL
    if not url:
        return False

    text = f"[{settings.ENVIRONMENT}] {source} — {message}"
    try:
        async with aiohttp.ClientSession(timeout=_TIMEOUT) as session:
            async with session.post(url, json={"text": text}) as response:
                if response.status >= 400:
                    logger.warning(
                        "Alert webhook answered HTTP %s for: %s",
                        response.status,
                        text,
                    )
                    return False
        return True
    except Exception:  # noqa: BLE001 — alerting must never break the caller
        logger.warning("Alert webhook unreachable for: %s", text, exc_info=True)
        return False
