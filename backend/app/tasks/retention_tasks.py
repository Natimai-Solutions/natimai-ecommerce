"""Nightly purge of the journals that only grow (functional audit, 2026-11).

- outbox events delivered (``DONE``) more than :data:`OUTBOX_DONE_DAYS` ago —
  the purge existed as a command line nobody scheduled;
- abandoned deliveries replayed or dismissed more than
  :data:`HANDLER_FAILURE_DAYS` ago;
- e-mail bodies after :data:`EMAIL_BODY_DAYS` (the row stays: who received
  what and when), e-mail rows after :data:`EMAIL_LOG_DAYS` — the journal kept
  every recipient and every message body for ever;
- supplier sync logs after :data:`SUPPLIER_SYNC_LOG_DAYS`.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, update
from sqlmodel import col
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine

logger = logging.getLogger(__name__)

OUTBOX_DONE_DAYS = 30
HANDLER_FAILURE_DAYS = 90
EMAIL_BODY_DAYS = 90
EMAIL_LOG_DAYS = 365
SUPPLIER_SYNC_LOG_DAYS = 90


def _rows(result: Any) -> int:
    count = getattr(result, "rowcount", 0)
    return count if isinstance(count, int) and count > 0 else 0


async def purge_journals(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """One purge; commits."""
    from app.features.integrations.crud.supplier_sync import supplier_sync_log_crud
    from app.features.notification.models.email_log import EmailLog
    from app.outbox.models import OutboxEvent, OutboxHandlerFailure

    current = now or datetime.now(UTC)
    stats = {
        "outbox_events": _rows(
            await session.execute(
                delete(OutboxEvent).where(
                    col(OutboxEvent.status) == "DONE",
                    col(OutboxEvent.updated_at)
                    < current - timedelta(days=OUTBOX_DONE_DAYS),
                )
            )
        ),
        "handler_failures": _rows(
            await session.execute(
                delete(OutboxHandlerFailure).where(
                    col(OutboxHandlerFailure.resolved_at).is_not(None),
                    col(OutboxHandlerFailure.resolved_at)
                    < current - timedelta(days=HANDLER_FAILURE_DAYS),
                )
            )
        ),
        "email_logs": _rows(
            await session.execute(
                delete(EmailLog).where(
                    col(EmailLog.created_at) < current - timedelta(days=EMAIL_LOG_DAYS)
                )
            )
        ),
        "email_bodies": _rows(
            await session.execute(
                update(EmailLog)
                .where(
                    col(EmailLog.created_at)
                    < current - timedelta(days=EMAIL_BODY_DAYS),
                    col(EmailLog.body_text).is_not(None)
                    | col(EmailLog.body_html).is_not(None),
                )
                .values(body_text=None, body_html=None, resendable=False)
            )
        ),
    }
    await session.commit()
    stats["supplier_sync_logs"] = int(
        await supplier_sync_log_crud.cleanup_old_logs(
            session, days_to_keep=SUPPLIER_SYNC_LOG_DAYS
        )
    )
    return stats


async def purge_journals_task(
    _ctx: dict[str, Any], *_a: Any, **_kw: Any
) -> dict[str, Any]:
    async with AsyncSession(engine) as session:
        stats = await purge_journals(session)
    logger.info("Journals purged: %s", stats)
    return {"status": "success", **stats}


def get_retention_cron_jobs() -> list[Any]:
    from arq import cron

    return [
        cron(
            purge_journals_task,  # type: ignore[arg-type]
            hour=4,
            minute=25,
            second=0,
            name="purge_journals",
        )
    ]
