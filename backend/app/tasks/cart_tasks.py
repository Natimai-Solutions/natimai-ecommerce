"""ARQ: hourly sweep of abandoned carts (Z3).

The sweep only publishes ``cart.abandoned`` events; the e-mail is the outbox
handler's job, so a mail provider outage retries on its own and never blocks
the sweep.
"""

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.features.cart.services.abandonment import remind_abandoned_carts

logger = logging.getLogger(__name__)


async def remind_abandoned_carts_task(
    _ctx: dict[str, Any], **_kwargs: Any
) -> dict[str, Any]:
    """Queue one reminder for every cart that went quiet."""
    if int(settings.CART_ABANDONMENT_REMINDER_DELAY_HOURS) <= 0:
        return {"status": "disabled"}
    async with AsyncSession(engine) as session:
        stats = await remind_abandoned_carts(session)
    logger.info("Abandoned cart sweep: %s", stats)
    return {"status": "ok", **stats}


def get_cart_abandonment_cron_jobs() -> list[Any]:
    """Hourly sweep, or nothing when the delay is 0."""
    if int(settings.CART_ABANDONMENT_REMINDER_DELAY_HOURS) <= 0:
        return []
    return [
        cron(
            remind_abandoned_carts_task,  # type: ignore[arg-type]
            minute=20,
            second=0,
            name="remind_abandoned_carts",
        )
    ]
