"""« État du système » : is the shop running, from the back office.

One or two people run the shop: a stopped worker, a failing supplier sync or
an expired e-mail key used to be learnt from a customer (functional audit,
November 2026). This page gathers what the alerts say: the last run of every
background task, the outbox backlog, the e-mails given up, the age of the
currency rates, whether alerts and e-mails can go out at all.
"""

from __future__ import annotations

import uuid
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func, update
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.config import settings
from app.features.departure.models import GroupedDeparture
from app.features.notification.models.email_log import STATUS_FAILED, EmailLog
from app.features.product.models.currency_rate import CurrencyRate
from app.features.system.models.task_run import TaskRun
from app.features.system.modules import module_enabled
from app.outbox.models import OutboxEvent, OutboxHandlerFailure

router = APIRouter(prefix="/admin/system-status", tags=["admin-dashboard"])

Level = Literal["ok", "warn", "error"]

#: A currency rate entered by hand older than this is flagged.
RATE_MAX_AGE_DAYS = 30
#: An outbox event still pending after this long means the poller is stuck.
OUTBOX_STUCK_MINUTES = 15
#: A scheduled task that has not started this long after its next expected
#: run: the worker is stopped or its scheduler no longer fires.
CRON_LATE_MINUTES = 20
#: Prefix of the keys the worker refreshes every ``health_check_interval``
#: (one per container, see ``WorkerSettings.health_check_key``).
WORKER_HEALTH_KEY_PREFIX = "arq:queue:health-check:"


class TaskRunPublic(BaseModel):
    name: str
    level: Level
    last_status: str | None
    last_started_at: datetime | None
    last_success_at: datetime | None
    last_failure_at: datetime | None
    last_error: str | None
    consecutive_failures: int
    runs: int
    #: When the next run was due (scheduled tasks only), and whether it is
    #: late: a stopped worker left every task « ok » on its last success.
    expected_by: datetime | None = None
    overdue: bool = False


class CurrencyRateAge(BaseModel):
    currency: str
    valid_from: date
    age_days: int
    level: Level


class AbandonedDelivery(BaseModel):
    id: uuid.UUID
    event_type: str
    handler: str
    error: str | None
    tries: int
    failed_at: datetime


class FailedEvent(BaseModel):
    """An outbox event the poller gave up on: its handlers never ran."""

    id: uuid.UUID
    event_type: str
    attempts: int
    error: str | None
    updated_at: datetime


class WaitingDeparture(BaseModel):
    """An open departure past its cut-off: its threshold is not reached, so
    nothing closed it, and until the admin decides the new orders are
    attached to no departure."""

    id: uuid.UUID
    name: str
    order_cutoff_at: datetime
    hours_past_cutoff: int


class SystemStatus(BaseModel):
    level: Level
    tasks: list[TaskRunPublic]
    outbox_pending: int
    outbox_oldest_pending_minutes: int | None
    outbox_failed: int
    #: Deliveries a handler gave up on (not replayed yet).
    outbox_abandoned: list[AbandonedDelivery]
    outbox_level: Level
    emails_failed_24h: int
    emails_queued_stuck: int
    email_level: Level
    currency_rates: list[CurrencyRateAge]
    alert_webhook_configured: bool
    email_provider_configured: bool
    departures_waiting: list[WaitingDeparture] = []
    departures_level: Level = "ok"
    outbox_failed_events: list[FailedEvent] = []
    #: A worker container refreshed its health key in Redis; None = Redis
    #: could not be asked.
    worker_alive: bool | None = None
    worker_level: Level = "ok"


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


def _cron_schedules() -> dict[str, Any]:
    """``{name: CronJob}`` of the worker's scheduled tasks."""
    try:
        from app.core.arq_worker import WorkerSettings

        return {job.name: job for job in WorkerSettings.cron_jobs}
    except Exception:  # noqa: BLE001 - the page never fails on it
        return {}


def _next_run(job: Any, after: datetime) -> datetime | None:
    """When ``job`` was due after ``after`` (UTC), per its cron fields."""
    from arq.cron import next_cron

    try:
        naive = after.astimezone(UTC).replace(tzinfo=None)
        due = next_cron(
            naive,
            month=job.month,
            day=job.day,
            weekday=job.weekday,
            hour=job.hour,
            minute=job.minute,
            second=job.second,
            microsecond=job.microsecond,
        )
    except Exception:  # noqa: BLE001
        return None
    return due.replace(tzinfo=UTC)


async def _worker_alive() -> bool | None:
    from app.core.rate_limit import shared_redis

    try:
        async for _key in shared_redis().scan_iter(
            match=f"{WORKER_HEALTH_KEY_PREFIX}*", count=100
        ):
            return True
    except Exception:  # noqa: BLE001 - unknown, not « down »
        return None
    return False


def _worst(levels: list[Level]) -> Level:
    if "error" in levels:
        return "error"
    if "warn" in levels:
        return "warn"
    return "ok"


@router.get("", response_model=SystemStatus)
async def get_system_status(
    session: SessionDep, _admin: CurrentSuperUser
) -> SystemStatus:
    now = datetime.now(UTC)

    schedules = _cron_schedules()
    tasks: list[TaskRunPublic] = []
    for row in (await session.exec(select(TaskRun).order_by(col(TaskRun.name)))).all():
        level: Level = "ok"
        if row.last_status == "failed":
            level = "error"
        elif row.last_status == "partial":
            level = "warn"
        started = _aware(row.last_started_at)
        job = schedules.get(row.name)
        expected = _next_run(job, started) if job is not None and started else None
        overdue = expected is not None and now > expected + timedelta(
            minutes=CRON_LATE_MINUTES
        )
        if overdue:
            level = "error"
        tasks.append(
            TaskRunPublic(
                name=row.name,
                level=level,
                last_status=row.last_status,
                last_started_at=_aware(row.last_started_at),
                last_success_at=_aware(row.last_success_at),
                last_failure_at=_aware(row.last_failure_at),
                last_error=row.last_error,
                consecutive_failures=row.consecutive_failures,
                runs=row.runs,
                expected_by=expected,
                overdue=overdue,
            )
        )

    pending, oldest = (
        await session.exec(
            select(func.count(), func.min(OutboxEvent.created_at)).where(
                col(OutboxEvent.status) == "PENDING"
            )
        )
    ).one()
    failed_events = (
        await session.exec(
            select(func.count()).where(col(OutboxEvent.status) == "FAILED")
        )
    ).one()
    abandoned = [
        AbandonedDelivery(
            id=row.id,
            event_type=row.event_type,
            handler=row.handler_path.rsplit(":", 1)[-1],
            error=row.error,
            tries=row.tries,
            failed_at=_aware(row.failed_at) or now,
        )
        for row in (
            await session.exec(
                select(OutboxHandlerFailure)
                .where(col(OutboxHandlerFailure.resolved_at).is_(None))
                .order_by(col(OutboxHandlerFailure.failed_at).desc())
                .limit(100)
            )
        ).all()
    ]
    oldest_minutes = (
        int((now - _aware(oldest)).total_seconds() // 60)  # type: ignore[operator]
        if oldest is not None
        else None
    )
    outbox_level: Level = "ok"
    if oldest_minutes is not None and oldest_minutes >= OUTBOX_STUCK_MINUTES:
        outbox_level = "error"
    elif abandoned:
        outbox_level = "error"
    elif failed_events:
        outbox_level = "warn"

    emails_failed = (
        await session.exec(
            select(func.count()).where(
                col(EmailLog.status) == STATUS_FAILED,
                col(EmailLog.created_at) >= now - timedelta(hours=24),
            )
        )
    ).one()
    emails_stuck = (
        await session.exec(
            select(func.count()).where(
                col(EmailLog.status) == "queued",
                col(EmailLog.created_at) <= now - timedelta(minutes=30),
            )
        )
    ).one()
    email_level: Level = (
        "error" if emails_stuck else ("warn" if emails_failed else "ok")
    )

    latest: dict[str, date] = {}
    for code, valid_from in (
        await session.exec(
            select(col(CurrencyRate.currency_code), col(CurrencyRate.valid_from)).where(
                col(CurrencyRate.is_active).is_(True)
            )
        )
    ).all():
        if code not in latest or valid_from > latest[code]:
            latest[code] = valid_from
    rates = []
    for code, valid_from in sorted(latest.items()):
        age = (now.date() - valid_from).days
        rates.append(
            CurrencyRateAge(
                currency=code,
                valid_from=valid_from,
                age_days=age,
                level="warn" if age > RATE_MAX_AGE_DAYS else "ok",
            )
        )

    departures_waiting: list[WaitingDeparture] = []
    if await module_enabled(session, "grouped_departures"):
        for departure in (
            await session.exec(
                select(GroupedDeparture)
                .where(
                    col(GroupedDeparture.is_active).is_(True),
                    col(GroupedDeparture.status) == "open",
                    col(GroupedDeparture.order_cutoff_at) <= now,
                )
                .order_by(col(GroupedDeparture.order_cutoff_at))
            )
        ).all():
            cutoff = _aware(departure.order_cutoff_at) or now
            departures_waiting.append(
                WaitingDeparture(
                    id=departure.id,
                    name=departure.name,
                    order_cutoff_at=cutoff,
                    hours_past_cutoff=int((now - cutoff).total_seconds() // 3600),
                )
            )
    departures_level: Level = "warn" if departures_waiting else "ok"

    failed_rows = (
        await session.exec(
            select(OutboxEvent)
            .where(col(OutboxEvent.status) == "FAILED")
            .order_by(col(OutboxEvent.updated_at).desc())
            .limit(100)
        )
    ).all()
    failed_list = [
        FailedEvent(
            id=row.id,
            event_type=row.type,
            attempts=row.attempts,
            error=row.last_error,
            updated_at=_aware(row.updated_at) or now,
        )
        for row in failed_rows
    ]
    alive = await _worker_alive()
    worker_level: Level = (
        "error" if alive is False else ("warn" if alive is None else "ok")
    )

    alert_configured = bool(settings.ALERT_WEBHOOK_URL)
    provider = settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
    email_configured = provider != "noop" and (
        provider != "mailgun" or bool(settings.MAILGUN_API_KEY)
    )
    overall = _worst(
        [t.level for t in tasks]
        + [outbox_level, email_level, departures_level, worker_level]
        + [r.level for r in rates]
        + ([] if alert_configured else ["warn"])
        + ([] if email_configured else ["warn"])
    )
    return SystemStatus(
        level=overall,
        tasks=tasks,
        outbox_pending=int(pending or 0),
        outbox_oldest_pending_minutes=oldest_minutes,
        outbox_failed=int(failed_events or 0),
        outbox_abandoned=abandoned,
        outbox_level=outbox_level,
        emails_failed_24h=int(emails_failed or 0),
        emails_queued_stuck=int(emails_stuck or 0),
        email_level=email_level,
        currency_rates=rates,
        alert_webhook_configured=alert_configured,
        email_provider_configured=email_configured,
        departures_waiting=departures_waiting,
        departures_level=departures_level,
        outbox_failed_events=failed_list,
        worker_alive=alive,
        worker_level=worker_level,
    )


class ReplayResponse(BaseModel):
    replayed: bool


@router.post("/abandoned/{failure_id}/replay", response_model=ReplayResponse)
async def replay_abandoned_delivery(
    failure_id: uuid.UUID, session: SessionDep, admin: CurrentSuperUser
) -> ReplayResponse:
    """Hand the abandoned delivery to the workers again (its handlers tolerate
    a replay: they are at-least-once by design)."""
    from app.core.arq_pool import get_arq_pool
    from app.core.errors import AppError

    # Claimed first, in one statement: two clicks (or two admins) both read
    # the row unresolved and both replayed it (review of 17/11/2026).
    claimed = (
        await session.exec(
            update(OutboxHandlerFailure)
            .where(
                col(OutboxHandlerFailure.id) == failure_id,
                col(OutboxHandlerFailure.resolved_at).is_(None),
            )
            .values(resolved_at=datetime.now(UTC), resolution=f"replayed by {admin.id}")
            .returning(
                col(OutboxHandlerFailure.handler_path),
                col(OutboxHandlerFailure.event_id),
                col(OutboxHandlerFailure.event_type),
                col(OutboxHandlerFailure.payload),
            )
        )
    ).first()
    if claimed is None:
        await session.rollback()
        raise AppError(
            code="outbox.failure.not_found",
            status_code=404,
            message="Handling not found or already replayed.",
            details={"id": str(failure_id)},
        )
    handler_path, event_id, event_type, payload = claimed
    pool = await get_arq_pool()  # type: ignore[no-untyped-call]
    try:
        await pool.enqueue_job(
            "execute_outbox_handler",
            handler_path=handler_path,
            event_id=str(event_id),
            event_type=event_type,
            payload=payload,
            _job_id=f"replay:{failure_id}",
        )
    except Exception:
        await session.rollback()  # not handed over: stays to replay
        raise
    finally:
        await pool.aclose()
    await session.commit()
    return ReplayResponse(replayed=True)


@router.post("/failed-events/{event_id}/replay", response_model=ReplayResponse)
async def replay_failed_event(
    event_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> ReplayResponse:
    """Give an event the poller gave up on back to it, attempts reset (its
    cause fixed: a provider back, a setting entered). Once only: a second
    click finds it pending already."""
    from app.core.errors import AppError

    result = await session.exec(
        update(OutboxEvent)
        .where(col(OutboxEvent.id) == event_id, col(OutboxEvent.status) == "FAILED")
        .values(
            status="PENDING",
            attempts=0,
            next_run_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    if not getattr(result, "rowcount", 0):
        await session.rollback()
        raise AppError(
            code="outbox.event.not_failed",
            status_code=404,
            message="Event not found or already replayed.",
            details={"id": str(event_id)},
        )
    await session.commit()
    return ReplayResponse(replayed=True)


@router.post("/failed-events/{event_id}/dismiss", response_model=ReplayResponse)
async def dismiss_failed_event(
    event_id: uuid.UUID, session: SessionDep, admin: CurrentSuperUser
) -> ReplayResponse:
    """Close an event that is not to be processed any more (handled by hand,
    obsolete): it leaves the page and the journal retention purges it."""
    from app.core.errors import AppError

    result = await session.exec(
        update(OutboxEvent)
        .where(col(OutboxEvent.id) == event_id, col(OutboxEvent.status) == "FAILED")
        .values(
            status="DONE",
            last_error=func.concat(
                f"écarté par {admin.id} — ", func.coalesce(OutboxEvent.last_error, "")
            ),
            updated_at=datetime.now(UTC),
        )
    )
    if not getattr(result, "rowcount", 0):
        await session.rollback()
        raise AppError(
            code="outbox.event.not_failed",
            status_code=404,
            message="Event not found or already replayed.",
            details={"id": str(event_id)},
        )
    await session.commit()
    return ReplayResponse(replayed=False)
