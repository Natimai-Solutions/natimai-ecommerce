"""Watchdog run by the worker: the outbox poller is another process.

When the poller stops, nothing alerted (functional audit, November 2026): the
health checker only looks at events already handed to the workers. Every ten
minutes the worker looks at the oldest event still waiting; past
:data:`STUCK_AFTER` the shop is alerted (at most once an hour).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.outbox.models import OutboxEvent

STUCK_AFTER = timedelta(minutes=15)
_ALERT_WINDOW_SECONDS = 3600


async def oldest_pending_age(session: AsyncSession, now: datetime) -> timedelta | None:
    oldest = (
        await session.exec(
            select(func.min(OutboxEvent.next_run_at)).where(
                col(OutboxEvent.status) == "PENDING",
                col(OutboxEvent.next_run_at) <= now,
            )
        )
    ).one()
    if oldest is None:
        return None
    if oldest.tzinfo is None:
        oldest = oldest.replace(tzinfo=UTC)
    return now - oldest


async def watch_outbox_backlog_task(
    _ctx: dict[str, Any], *_a: Any, **_kw: Any
) -> dict[str, Any]:
    now = datetime.now(UTC)
    async with AsyncSession(engine) as session:
        age = await oldest_pending_age(session, now)
    minutes = int(age.total_seconds() // 60) if age is not None else 0
    if age is None or age < STUCK_AFTER:
        return {"status": "success", "oldest_pending_minutes": minutes}
    try:
        from app.core.rate_limit import shared_redis

        first = await shared_redis().set(
            "alert:outbox_stuck", "1", nx=True, ex=_ALERT_WINDOW_SECONDS
        )
    except Exception:  # noqa: BLE001
        first = True
    if first:
        from app.core.operator_messages import alert

        await alert("outbox.stuck", source="outbox", minutes=minutes)
    return {"status": "error", "message": f"outbox stuck for {minutes} min"}


def get_watch_cron_jobs() -> list[Any]:
    from arq import cron

    return [
        cron(
            watch_outbox_backlog_task,  # type: ignore[arg-type]
            minute=set(range(4, 60, 10)),
            second=0,
            name="watch_outbox_backlog",
        )
    ]
