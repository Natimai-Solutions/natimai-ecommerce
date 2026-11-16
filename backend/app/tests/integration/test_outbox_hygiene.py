"""Integration (real DB): an abandoned delivery is kept and listed; the
journals that only grew are purged (functional audit, November 2026)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.notification.models.email_log import EmailLog
from app.outbox import consumer
from app.outbox.models import OutboxEvent, OutboxHandlerFailure
from app.tasks.retention_tasks import purge_journals


@pytest.mark.asyncio
async def test_an_abandoned_delivery_is_recorded(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(consumer, "engine", db_session.bind)
    event_id = str(uuid.uuid4())
    await consumer._record_abandoned(  # noqa: SLF001
        event_id,
        "payment.captured",
        "app.handlers.payment:on_payment_captured",
        {"order_id": "x"},
        "boom",
        8,
    )
    rows = (await db_session.exec(select(OutboxHandlerFailure))).all()
    assert [(str(r.event_id), r.tries, r.resolved_at) for r in rows] == [
        (event_id, 8, None)
    ]


@pytest.mark.asyncio
async def test_old_journals_are_purged(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=400)
    db_session.add_all(
        [
            OutboxEvent(type="x", payload={}, status="DONE", updated_at=old),
            OutboxEvent(type="x", payload={}, status="PENDING", updated_at=old),
            OutboxEvent(type="x", payload={}, status="DONE", updated_at=now),
            EmailLog(
                event_type="t", recipient="a@b.c", body_text="secret", created_at=old
            ),
            EmailLog(
                event_type="t",
                recipient="a@b.c",
                body_text="kept short",
                created_at=now - timedelta(days=100),
            ),
        ]
    )
    await db_session.commit()

    stats = await purge_journals(db_session, now=now)

    assert stats["outbox_events"] == 1  # the old DONE one; PENDING is never purged
    assert stats["email_logs"] == 1 and stats["email_bodies"] == 1
    remaining = (await db_session.exec(select(EmailLog))).all()
    assert [(e.body_text, e.resendable) for e in remaining] == [(None, False)]
