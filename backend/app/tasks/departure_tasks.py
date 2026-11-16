"""ARQ task: post the grouped-departure reminders that are due (every 15 min)."""

from __future__ import annotations

import logging
from typing import Any

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.departure.services import (
    close_due_departures,
    publish_due_reminders,
)
from app.features.system.modules import module_enabled

logger = logging.getLogger(__name__)


async def publish_departure_reminders_task(_ctx: dict[str, Any]) -> dict[str, int]:
    """Cron entry point: one pass over the due reminders."""
    async with AsyncSession(engine) as session:
        if not await module_enabled(session, "grouped_departures"):
            return {}
        result = await publish_due_reminders(session)
    logger.info("Departure reminders: %s", result)
    return result


async def close_due_departures_task(_ctx: dict[str, Any]) -> dict[str, Any]:
    """Cron: close the departures whose cut-off has passed; tell the shop about
    those left open below their threshold (once, at the first tick past it)."""
    async with AsyncSession(engine) as session:
        if not await module_enabled(session, "grouped_departures"):
            return {}
        result = await close_due_departures(session)
    waiting = result["below_threshold"]
    if waiting:
        await _alert_below_threshold(waiting)
    logger.info("Departures past their cut-off: %s", result)
    return {
        "status": "success",
        "closed": len(result["closed"]),
        "waiting": len(waiting),
    }


async def _alert_below_threshold(names: list[str]) -> None:
    from app.core.alerting import send_alert
    from app.core.rate_limit import shared_redis

    fresh: list[str] = []
    for name in names:
        try:
            first = await shared_redis().set(
                f"alert:departure_threshold:{name}", "1", nx=True, ex=7 * 24 * 3600
            )
        except Exception:  # noqa: BLE001 - no Redis: tell anyway
            first = True
        if first:
            fresh.append(name)
    if fresh:
        await send_alert(
            "Date limite passée, seuil non atteint : "
            + ", ".join(f"« {n} »" for n in fresh)
            + ". Clôturez (en forçant) ou repoussez la date depuis « Départs groupés » ;"
            " d'ici là les nouvelles commandes ne sont rattachées à aucun départ.",
            source="departures",
        )


def get_departure_cron_jobs() -> list[Any]:
    """Every 15 minutes: a reminder posts within a quarter of an hour of its time."""
    return [
        cron(
            publish_departure_reminders_task,  # type: ignore[arg-type]
            minute={0, 15, 30, 45},
            second=0,
            name="publish_departure_reminders",
        ),
        cron(
            close_due_departures_task,  # type: ignore[arg-type]
            minute={2, 17, 32, 47},
            second=0,
            name="close_due_departures",
        ),
    ]
