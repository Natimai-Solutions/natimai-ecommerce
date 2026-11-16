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

import functools
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

logger = logging.getLogger(__name__)

#: A task that keeps failing is reported again after this long.
REALERT_AFTER = timedelta(hours=6)

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
    if status in {"error", "failed", "failure"}:
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
            alert = (
                row.consecutive_failures == 1
                or last is None
                or (now - last >= REALERT_AFTER)
            )
            if alert:
                row.last_alert_at = now
        session.add(row)
        await session.commit()
        return alert


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
        from app.core.alerting import send_alert

        label = (
            "a échoué" if status == STATUS_FAILED else "s'est terminée avec des erreurs"
        )
        await send_alert(
            f"Tâche « {name} » {label} : {(error or '')[:300]}", source="tasks"
        )
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
        except Exception as exc:
            await record_run(key, STATUS_FAILED, f"{type(exc).__name__}: {exc}")
            raise
        status, error = outcome_of(result)
        await record_run(key, status, error, result)
        return result

    return wrapper
