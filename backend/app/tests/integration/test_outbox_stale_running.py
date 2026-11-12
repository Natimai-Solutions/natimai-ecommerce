"""An event a dead poller left RUNNING is delivered again (audit 2026-11)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.outbox.models import OutboxEvent
from app.outbox.poller import _release_stale_running


@pytest.mark.asyncio
async def test_a_stale_running_event_goes_back_to_pending(
    db_session: AsyncSession,
) -> None:
    stale = OutboxEvent(type="payment.captured", payload={}, status="RUNNING")
    stale.updated_at = datetime.now(UTC) - timedelta(minutes=30)
    fresh = OutboxEvent(type="payment.captured", payload={}, status="RUNNING")
    db_session.add_all([stale, fresh])
    stale_id, fresh_id = stale.id, fresh.id
    await db_session.commit()

    await _release_stale_running(db_session)

    db_session.expire_all()
    reloaded = await db_session.get(OutboxEvent, stale_id)
    still = await db_session.get(OutboxEvent, fresh_id)
    assert reloaded is not None and reloaded.status == "PENDING"
    # One being enqueued right now is left alone.
    assert still is not None and still.status == "RUNNING"
