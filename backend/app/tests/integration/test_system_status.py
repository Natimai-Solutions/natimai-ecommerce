"""Integration (real DB): « État du système » tells a stopped worker, a cron
that no longer fires and the events the poller gave up on — and a replay
happens once.

Review of 17/11/2026: a stopped worker or a cron that no longer fired left
every task « ok » on its last success; FAILED outbox events had neither
replay nor purge; two clicks on « Rejouer » replayed twice."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import admin_system_status as status_routes
from app.core.errors import AppError
from app.features.system.models.task_run import TaskRun
from app.outbox.models import OutboxEvent, OutboxHandlerFailure

ADMIN: Any = SimpleNamespace(id=uuid.uuid4(), is_superuser=True)


@pytest.fixture(autouse=True)
def _worker_up(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(status_routes, "_worker_alive", AsyncMock(return_value=True))
    monkeypatch.setattr(status_routes, "module_enabled", AsyncMock(return_value=False))


@pytest.mark.asyncio
async def test_a_cron_that_no_longer_fires_is_overdue(db_session: AsyncSession) -> None:
    now = datetime.now(UTC)
    # Every 15 minutes; last started two hours ago, successfully.
    db_session.add_all(
        [
            TaskRun(
                name="close_due_departures",
                last_status="ok",
                last_started_at=now - timedelta(hours=2),
                last_success_at=now - timedelta(hours=2),
                runs=10,
            ),
            TaskRun(
                name="publish_departure_reminders",
                last_status="ok",
                last_started_at=now - timedelta(minutes=5),
                last_success_at=now - timedelta(minutes=5),
                runs=10,
            ),
        ]
    )
    await db_session.commit()

    page = await status_routes.get_system_status(db_session, ADMIN)

    by_name = {t.name: t for t in page.tasks}
    late = by_name["close_due_departures"]
    assert late.overdue is True and late.level == "error"
    assert late.expected_by is not None and late.expected_by < now
    fresh = by_name["publish_departure_reminders"]
    assert fresh.overdue is False and fresh.level == "ok"
    assert page.level == "error"


@pytest.mark.asyncio
async def test_a_stopped_worker_is_an_error(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(status_routes, "_worker_alive", AsyncMock(return_value=False))

    page = await status_routes.get_system_status(db_session, ADMIN)

    assert page.worker_alive is False and page.worker_level == "error"
    assert page.level == "error"


@pytest.mark.asyncio
async def test_a_failed_event_is_listed_then_replayed_once_or_dismissed(
    db_session: AsyncSession,
) -> None:
    replayable = OutboxEvent(
        type="payment.captured", payload={}, status="FAILED", attempts=8
    )
    obsolete = OutboxEvent(type="cart.abandoned", payload={}, status="FAILED")
    db_session.add_all([replayable, obsolete])
    await db_session.flush()
    replay_id, dismiss_id = replayable.id, obsolete.id
    await db_session.commit()

    page = await status_routes.get_system_status(db_session, ADMIN)
    assert {e.id for e in page.outbox_failed_events} == {replay_id, dismiss_id}

    await status_routes.replay_failed_event(replay_id, db_session, ADMIN)
    with pytest.raises(AppError) as twice:
        await status_routes.replay_failed_event(replay_id, db_session, ADMIN)
    assert twice.value.code == "outbox.event.not_failed"
    db_session.expire_all()
    again = await db_session.get(OutboxEvent, replay_id)
    assert again is not None and again.status == "PENDING" and again.attempts == 0

    await status_routes.dismiss_failed_event(dismiss_id, db_session, ADMIN)
    db_session.expire_all()
    closed = await db_session.get(OutboxEvent, dismiss_id)
    assert closed is not None and closed.status == "DONE"
    assert closed.last_error is not None and closed.last_error.startswith("écarté")

    page = await status_routes.get_system_status(db_session, ADMIN)
    assert page.outbox_failed_events == []


@pytest.mark.asyncio
async def test_an_abandoned_delivery_is_replayed_once(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    enqueued: list[str] = []

    class Pool:
        async def enqueue_job(self, _name: str, **kwargs: Any) -> None:
            enqueued.append(str(kwargs["_job_id"]))

        async def aclose(self) -> None:
            return None

    async def pool() -> Pool:
        return Pool()

    monkeypatch.setattr("app.core.arq_pool.get_arq_pool", pool)
    failure = OutboxHandlerFailure(
        event_id=uuid.uuid4(),
        event_type="payment.captured",
        handler_path="app.handlers.payment:on_payment_captured",
        payload={"order_id": "x"},
        error="boom",
        tries=8,
    )
    db_session.add(failure)
    await db_session.flush()
    failure_id = failure.id
    await db_session.commit()

    await status_routes.replay_abandoned_delivery(failure_id, db_session, ADMIN)
    with pytest.raises(AppError) as twice:
        await status_routes.replay_abandoned_delivery(failure_id, db_session, ADMIN)

    assert twice.value.code == "outbox.failure.not_found"
    assert enqueued == [f"replay:{failure_id}"]
