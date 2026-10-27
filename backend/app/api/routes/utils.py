import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import col, func, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.observability import get_checkout_metrics_snapshot
from app.features.order.models.order import Order
from app.features.payment.models.payment import Payment
from app.outbox.models import OutboxEvent

router = APIRouter()


@router.get("/health-check", tags=["utils"])
async def health_check() -> bool:
    """Execute health check."""
    return True


class TaskStatus(BaseModel):
    """Represents task status."""

    task_id: uuid.UUID
    finished: bool
    success: bool
    state: str


class CheckoutObservabilityMetrics(BaseModel):
    """Represents checkout observability metrics."""

    window_minutes: int
    attempts: int
    successes: int
    failures: int
    failure_rate: float
    avg_duration_ms: float
    p95_duration_ms: int | None
    alert_checkout_errors: bool
    recent_failure_codes: list[str] = Field(default_factory=list)


class OutboxObservabilityMetrics(BaseModel):
    """Represents outbox observability metrics."""

    pending: int
    running: int
    done: int
    failed: int
    stale_pending: int
    oldest_pending_age_minutes: float | None


class CommerceObservabilityMetrics(BaseModel):
    """Represents commerce observability metrics."""

    orders_total: int
    orders_last_24h: int
    payments_total: int
    payments_last_24h: int


class ObservabilityDashboard(BaseModel):
    """Represents observability dashboard."""

    generated_at: datetime
    commerce: CommerceObservabilityMetrics
    outbox_jobs: OutboxObservabilityMetrics
    checkout: CheckoutObservabilityMetrics


async def _collect_commerce_metrics(
    session: SessionDep,
    *,
    now: datetime,
) -> CommerceObservabilityMetrics:
    """Execute collect commerce metrics."""
    since_24h = now - timedelta(hours=24)

    orders_total_result = await session.exec(
        select(func.count()).select_from(Order).where(col(Order.is_active).is_(True))
    )
    orders_last_24h_result = await session.exec(
        select(func.count())
        .select_from(Order)
        .where(
            col(Order.is_active).is_(True),
            col(Order.created_at) >= since_24h,
        )
    )

    payments_total_result = await session.exec(
        select(func.count())
        .select_from(Payment)
        .where(col(Payment.is_active).is_(True))
    )
    payments_last_24h_result = await session.exec(
        select(func.count())
        .select_from(Payment)
        .where(
            col(Payment.is_active).is_(True),
            col(Payment.created_at) >= since_24h,
        )
    )

    return CommerceObservabilityMetrics(
        orders_total=int(orders_total_result.one() or 0),
        orders_last_24h=int(orders_last_24h_result.one() or 0),
        payments_total=int(payments_total_result.one() or 0),
        payments_last_24h=int(payments_last_24h_result.one() or 0),
    )


async def _collect_outbox_metrics(
    session: SessionDep,
    *,
    now: datetime,
) -> OutboxObservabilityMetrics:
    """Execute collect outbox metrics."""
    status_counts_result = await session.exec(
        select(OutboxEvent.status, func.count()).group_by(OutboxEvent.status)
    )
    status_counts = {status: int(count) for status, count in status_counts_result.all()}

    stale_cutoff = now - timedelta(minutes=15)
    stale_pending_result = await session.exec(
        select(func.count())
        .select_from(OutboxEvent)
        .where(
            OutboxEvent.status == "PENDING",
            col(OutboxEvent.created_at) <= stale_cutoff,
        )
    )

    oldest_pending_result = await session.exec(
        select(OutboxEvent.created_at)
        .where(OutboxEvent.status == "PENDING")
        .order_by(col(OutboxEvent.created_at).asc())
        .limit(1)
    )
    oldest_pending_created_at = oldest_pending_result.first()

    oldest_pending_age_minutes: float | None = None
    if oldest_pending_created_at is not None:
        oldest_pending_age_minutes = round(
            max((now - oldest_pending_created_at).total_seconds(), 0.0) / 60.0,
            2,
        )

    return OutboxObservabilityMetrics(
        pending=status_counts.get("PENDING", 0),
        running=status_counts.get("RUNNING", 0),
        done=status_counts.get("DONE", 0),
        failed=status_counts.get("FAILED", 0),
        stale_pending=int(stale_pending_result.one() or 0),
        oldest_pending_age_minutes=oldest_pending_age_minutes,
    )


@router.get(
    "/observability/dashboard",
    tags=["utils"],
    response_model=ObservabilityDashboard,
)
async def get_observability_dashboard(
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> ObservabilityDashboard:
    """Get observability dashboard (superuser only — business metrics)."""
    now = datetime.now(UTC)
    commerce_metrics = await _collect_commerce_metrics(session, now=now)
    outbox_metrics = await _collect_outbox_metrics(session, now=now)
    checkout_snapshot = await get_checkout_metrics_snapshot(window_minutes=60)

    checkout_metrics = CheckoutObservabilityMetrics(
        window_minutes=int(checkout_snapshot["window_minutes"]),
        attempts=int(checkout_snapshot["attempts"]),
        successes=int(checkout_snapshot["successes"]),
        failures=int(checkout_snapshot["failures"]),
        failure_rate=float(checkout_snapshot["failure_rate"]),
        avg_duration_ms=float(checkout_snapshot["avg_duration_ms"]),
        p95_duration_ms=(
            int(checkout_snapshot["p95_duration_ms"])
            if checkout_snapshot["p95_duration_ms"] is not None
            else None
        ),
        alert_checkout_errors=bool(checkout_snapshot["alert_checkout_errors"]),
        recent_failure_codes=[
            str(code) for code in checkout_snapshot.get("recent_failure_codes", [])
        ],
    )

    return ObservabilityDashboard(
        generated_at=now,
        commerce=commerce_metrics,
        outbox_jobs=outbox_metrics,
        checkout=checkout_metrics,
    )


# @router.get(
#    "/task-check/{task_id}", tags=["utils"], response_model=TaskStatus
# )
# async def check_tasks(
#    task_id: uuid.UUID,
# ) -> TaskStatus:
#    task = celery_app.AsyncResult(str(task_id))
#    return TaskStatus(
#        task_id=task_id,
#        finished=task.ready(),
#        success=task.successful(),
#        state=task.state,
#   )
