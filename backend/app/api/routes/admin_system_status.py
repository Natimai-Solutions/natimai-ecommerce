"""« État du système » : is the shop running, from the back office.

One or two people run the shop: a stopped worker, a failing supplier sync or
an expired e-mail key used to be learnt from a customer (functional audit,
November 2026). This page gathers what the alerts say: the last run of every
background task, the outbox backlog, the e-mails given up, the age of the
currency rates, whether alerts and e-mails can go out at all.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from typing import Literal

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.config import settings
from app.features.notification.models.email_log import STATUS_FAILED, EmailLog
from app.features.product.models.currency_rate import CurrencyRate
from app.features.system.models.task_run import TaskRun
from app.outbox.models import OutboxEvent

router = APIRouter(prefix="/admin/system-status", tags=["admin-dashboard"])

Level = Literal["ok", "warn", "error"]

#: A currency rate entered by hand older than this is flagged.
RATE_MAX_AGE_DAYS = 30
#: An outbox event still pending after this long means the poller is stuck.
OUTBOX_STUCK_MINUTES = 15


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


class CurrencyRateAge(BaseModel):
    currency: str
    valid_from: date
    age_days: int
    level: Level


class SystemStatus(BaseModel):
    level: Level
    tasks: list[TaskRunPublic]
    outbox_pending: int
    outbox_oldest_pending_minutes: int | None
    outbox_failed: int
    outbox_level: Level
    emails_failed_24h: int
    emails_queued_stuck: int
    email_level: Level
    currency_rates: list[CurrencyRateAge]
    alert_webhook_configured: bool
    email_provider_configured: bool


def _aware(moment: datetime | None) -> datetime | None:
    if moment is None:
        return None
    return moment if moment.tzinfo is not None else moment.replace(tzinfo=UTC)


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

    tasks: list[TaskRunPublic] = []
    for row in (await session.exec(select(TaskRun).order_by(col(TaskRun.name)))).all():
        level: Level = "ok"
        if row.last_status == "failed":
            level = "error"
        elif row.last_status == "partial":
            level = "warn"
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
    oldest_minutes = (
        int((now - _aware(oldest)).total_seconds() // 60)  # type: ignore[operator]
        if oldest is not None
        else None
    )
    outbox_level: Level = "ok"
    if oldest_minutes is not None and oldest_minutes >= OUTBOX_STUCK_MINUTES:
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

    alert_configured = bool(settings.ALERT_WEBHOOK_URL)
    provider = settings.PAYMENT_NOTIFICATIONS_EMAIL_PROVIDER
    email_configured = provider != "noop" and (
        provider != "mailgun" or bool(settings.MAILGUN_API_KEY)
    )
    overall = _worst(
        [t.level for t in tasks]
        + [outbox_level, email_level]
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
        outbox_level=outbox_level,
        emails_failed_24h=int(emails_failed or 0),
        emails_queued_stuck=int(emails_stuck or 0),
        email_level=email_level,
        currency_rates=rates,
        alert_webhook_configured=alert_configured,
        email_provider_configured=email_configured,
    )
