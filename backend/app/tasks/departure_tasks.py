"""ARQ task: post the grouped-departure reminders that are due (every 15 min)."""

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.departure.services import publish_due_reminders

logger = logging.getLogger(__name__)


async def publish_departure_reminders_task(_ctx: dict[str, Any]) -> dict[str, int]:
    """Cron entry point: one pass over the due reminders."""
    async with AsyncSession(engine) as session:
        result = await publish_due_reminders(session)
    logger.info("Departure reminders: %s", result)
    return result


def get_departure_cron_jobs() -> list[Any]:
    """Every 15 minutes: a reminder posts within a quarter of an hour of its time."""
    return [
        cron(
            publish_departure_reminders_task,  # type: ignore[arg-type]
            minute={0, 15, 30, 45},
            second=0,
            name="publish_departure_reminders",
        )
    ]
