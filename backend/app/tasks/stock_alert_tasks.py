"""ARQ task: e-mail the « me prévenir » alerts whose product is back (hourly)."""

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.product.services.stock_alert import notify_due_alerts

logger = logging.getLogger(__name__)


async def notify_stock_alerts_task(_ctx: dict[str, Any]) -> dict[str, int]:
    """Cron entry point: one pass over the pending alerts."""
    async with AsyncSession(engine) as session:
        result = await notify_due_alerts(session)
    logger.info("Stock alerts: %s", result)
    return result


def get_stock_alert_cron_jobs() -> list[Any]:
    """Hourly, after the supplier price/stock sync (every 2 h) has landed."""
    return [
        cron(
            notify_stock_alerts_task,  # type: ignore[arg-type]
            minute=20,
            second=0,
            name="notify_stock_alerts",
        )
    ]
