"""Record every run of the background tasks, alert when one fails.

:func:`journaled` wraps an ARQ task: the run is written to ``task_runs``
(started, finished, ok / partial / failed, the result or the error) and a
failure posts to ``ALERT_WEBHOOK_URL`` — on the first failure, then at most
every :data:`REALERT_AFTER` while it keeps failing. A task that reports its
own failure in its result (``{"status": "error"}``, ``"errors": 3``) counts
too: the price and stock sync used to return « success » with errors, and
the nightly price refresh only logged its exception.

The journal never breaks the task: a database or webhook error while
recording is logged and swallowed.
"""

from __future__ import annotations

import asyncio
import functools
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)

#: A task that keeps failing is reported again after this long.
REALERT_AFTER = timedelta(hours=6)
#: A task that fails again right after a success stays quiet this long.
FLAPPING_QUIET = timedelta(hours=1)

STATUS_OK = "ok"
STATUS_PARTIAL = "partial"
STATUS_FAILED = "failed"

TaskFn = Callable[..., Awaitable[Any]]


def _now() -> datetime:
    return datetime.now(UTC)


def _engine() -> Any:
    from app.core.db import engine

    return engine


def outcome_of(result: Any) -> tuple[str, str | None]:
    """``(status, error)`` read from what a task returned."""
    if not isinstance(result, dict):
        return STATUS_OK, None
    status = str(result.get("status") or "").lower()
    # « unhealthy »: the supplier health probe answers that way, and its
    # failure alerted nobody (review of 17/11/2026).
    if status in {"error", "failed", "failure", "unhealthy"}:
        return STATUS_FAILED, str(
            result.get("message") or result.get("error") or status
        )
    errors = result.get("errors")
    if isinstance(errors, int) and errors > 0:
        return STATUS_PARTIAL, f"{errors} erreur(s) pendant l'exécution"
    if isinstance(errors, list) and errors:
        return STATUS_PARTIAL, f"{len(errors)} erreur(s) pendant l'exécution"
    return STATUS_OK, None


def _jsonable(result: Any) -> dict[str, Any] | None:
    if not isinstance(result, dict):
        return None
    out: dict[str, Any] = {}
    for key, value in list(result.items())[:30]:
        if isinstance(value, str | int | float | bool) or value is None:
            out[str(key)] = value if not isinstance(value, str) else value[:300]
    return out


def run_name(name: str, kwargs: dict[str, Any]) -> str:
    """The journal key: the task, and the supplier it ran for."""
    supplier = kwargs.get("supplier_name") or kwargs.get("supplier_code")
    return f"{name}:{supplier}" if supplier else name


async def _record_start(name: str) -> None:
    from app.features.system.models.task_run import TaskRun

    async with AsyncSession(_engine()) as session:
        row = await session.get(TaskRun, name)
        if row is None:
            row = TaskRun(name=name)
        row.last_started_at = _now()
        row.updated_at = _now()
        session.add(row)
        await session.commit()


async def _record_end(name: str, status: str, error: str | None, result: Any) -> bool:
    """Write the run's end; True when an alert is due."""
    from app.features.system.models.task_run import TaskRun

    now = _now()
    async with AsyncSession(_engine()) as session:
        row = await session.get(TaskRun, name)
        if row is None:
            row = TaskRun(name=name)
        row.runs = (row.runs or 0) + 1
        row.last_finished_at = now
        row.last_status = status
        row.last_result = _jsonable(result)
        row.updated_at = now
        alert = False
        if status == STATUS_OK:
            row.last_success_at = now
            row.last_error = None
            row.consecutive_failures = 0
        else:
            row.last_failure_at = now
            row.last_error = (error or "")[:2000]
            row.failures = (row.failures or 0) + 1
            row.consecutive_failures = (row.consecutive_failures or 0) + 1
            last = row.last_alert_at
            if last is not None and last.tzinfo is None:
                last = last.replace(tzinfo=UTC)
            # A new incident alerts at once — unless one was sent within the
            # hour: a task that alternates success and failure alerted on
            # every other run.
            # Stamped once the alert is out (``_mark_alerted``): stamped
            # before, a webhook down at that moment silenced the task for
            # the next 6 hours.
            alert = (
                last is None
                or (now - last >= REALERT_AFTER)
                or (row.consecutive_failures == 1 and now - last >= FLAPPING_QUIET)
            )
        session.add(row)
        await session.commit()
        return alert


async def _mark_alerted(name: str) -> None:
    from app.features.system.models.task_run import TaskRun

    async with AsyncSession(_engine()) as session:
        row = await session.get(TaskRun, name)
        if row is not None:
            row.last_alert_at = _now()
            session.add(row)
            await session.commit()


async def record_run(
    name: str, status: str, error: str | None = None, result: Any = None
) -> None:
    """Record a finished run and alert when due. Never raises."""
    try:
        alert = await _record_end(name, status, error, result)
    except Exception:  # noqa: BLE001 - the journal never breaks a task
        logger.warning("Task run of %s not recorded", name, exc_info=True)
        alert = status != STATUS_OK
    if not alert:
        return
    try:
        from app.core.operator_messages import alert as post_alert

        sent = await post_alert(
            "tasks.failed" if status == STATUS_FAILED else "tasks.partial",
            source="tasks",
            name=name,
            error=(error or "")[:300],
        )
        if sent:
            await _mark_alerted(name)
    except Exception:  # noqa: BLE001
        logger.warning("Alert for task %s not sent", name, exc_info=True)


def journaled(fn: TaskFn, name: str | None = None) -> TaskFn:
    """``fn`` with its runs written to the journal (ARQ task or cron)."""
    task_name: str = name or str(getattr(fn, "__name__", "task"))

    @functools.wraps(fn)
    async def wrapper(ctx: Any, *args: Any, **kwargs: Any) -> Any:
        key = run_name(task_name, kwargs)
        try:
            await _record_start(key)
        except Exception:  # noqa: BLE001
            logger.warning("Task start of %s not recorded", key, exc_info=True)
        try:
            result = await fn(ctx, *args, **kwargs)
        except asyncio.CancelledError:
            # arq enforces its job timeout by cancelling the task (and a
            # stopping worker does the same): not an ``Exception``, so the run
            # stayed « ok » from its last success and nobody was told.
            try:
                await asyncio.shield(
                    record_run(key, STATUS_FAILED, "interrompue (délai ou arrêt)")
                )
            except BaseException:  # noqa: BLE001 - the cancellation goes on
                logger.warning("Cancelled run of %s not recorded", key)
            raise
        except Exception as exc:
            await record_run(key, STATUS_FAILED, f"{type(exc).__name__}: {exc}")
            raise
        status, error = outcome_of(result)
        await record_run(key, status, error, result)
        return result

    return wrapper


def _abandoned_job(result_data: bytes | None) -> tuple[str, str] | None:
    """``(function, reason)`` of a job arq gave up on before running it."""
    if not result_data:
        return None
    from arq.jobs import deserialize_result

    try:
        info = deserialize_result(result_data)
    except Exception:  # noqa: BLE001
        return None
    name = run_name(info.function, dict(info.kwargs or {}))
    return name, f"abandonnée avant exécution : {info.result!r}"[:2000]


def install_abandoned_job_journal() -> None:
    """Journal (and alert on) the jobs arq gives up on without running them.

    A job expired in the queue, past its tries before it could start, or
    whose function is unknown never reaches :func:`journaled`: arq only
    stores a failed result, read by no one, and « État du système » kept the
    task « ok » (review of 17/11/2026). ``Worker.finish_failed_job`` is the
    one path of those cases (a job that ran and failed goes through
    ``finish_job``): it is wrapped to record them. Idempotent.
    """
    from arq.worker import Worker

    original = Worker.finish_failed_job
    if getattr(original, "_journaled", False):
        return

    async def finish_failed_job(
        self: Any, job_id: str, result_data: bytes | None
    ) -> None:
        await original(self, job_id, result_data)
        abandoned = _abandoned_job(result_data)
        if abandoned is not None:
            name, reason = abandoned
            await record_run(name, STATUS_FAILED, reason)

    finish_failed_job._journaled = True  # type: ignore[attr-defined]
    Worker.finish_failed_job = finish_failed_job  # type: ignore[method-assign]
