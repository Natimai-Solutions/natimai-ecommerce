"""Integration (real DB): the background tasks are journaled and a failure
alerts (functional audit, November 2026: they failed with a log line)."""

from __future__ import annotations

from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import task_runs
from app.features.system.models.task_run import TaskRun


@pytest.mark.asyncio
async def test_runs_are_journaled_and_failures_alert(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    alerts: list[str] = []

    async def _alert(message: str, **_kwargs: object) -> bool:
        alerts.append(message)
        return True

    monkeypatch.setattr("app.core.alerting.send_alert", _alert)
    # The journal writes with its own session, on the test database here.
    monkeypatch.setattr(task_runs, "_engine", lambda: db_session.bind)

    async def sync(_ctx: Any, **_kwargs: Any) -> dict[str, Any]:
        return {"status": "success", "errors": 2, "updated": 10}

    async def refresh(_ctx: Any) -> dict[str, Any]:
        raise RuntimeError("database gone")

    async def fine(_ctx: Any) -> dict[str, Any]:
        return {"status": "success"}

    await task_runs.journaled(sync, "inventory")({}, supplier_name="ingram")
    with pytest.raises(RuntimeError):
        await task_runs.journaled(refresh, "prices")({})
    with pytest.raises(RuntimeError):
        await task_runs.journaled(refresh, "prices")({})
    await task_runs.journaled(fine, "fine")({})

    db_session.expire_all()
    partial = await db_session.get(TaskRun, "inventory:ingram")
    failed = await db_session.get(TaskRun, "prices")
    ok = await db_session.get(TaskRun, "fine")
    assert partial is not None and partial.last_status == "partial"
    assert failed is not None and failed.last_status == "failed"
    assert failed.consecutive_failures == 2 and "database gone" in (
        failed.last_error or ""
    )
    assert ok is not None and ok.last_status == "ok" and ok.last_success_at
    # One alert per failing task, not one per run.
    assert len(alerts) == 2
    assert any("inventory:ingram" in a for a in alerts)


@pytest.mark.asyncio
async def test_an_alert_that_did_not_go_out_is_tried_again(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Review of 17/11/2026: ``last_alert_at`` was stamped before sending, so
    a webhook down at that moment silenced the failing task for 6 hours."""
    delivered = {"ok": False}
    alerts: list[str] = []

    async def _alert(message: str, **_kwargs: object) -> bool:
        alerts.append(message)
        return delivered["ok"]

    monkeypatch.setattr("app.core.alerting.send_alert", _alert)
    monkeypatch.setattr(task_runs, "_engine", lambda: db_session.bind)

    async def broken(_ctx: Any) -> dict[str, Any]:
        return {"status": "error", "message": "API down"}

    await task_runs.journaled(broken, "health")({})
    row = await db_session.get(TaskRun, "health")
    assert row is not None and row.last_alert_at is None

    delivered["ok"] = True
    await task_runs.journaled(broken, "health")({})
    assert len(alerts) == 2  # tried again on the next failure
    db_session.expire_all()
    row = await db_session.get(TaskRun, "health")
    assert row is not None and row.last_alert_at is not None

    await task_runs.journaled(broken, "health")({})
    assert len(alerts) == 2  # now quiet until REALERT_AFTER


def test_an_unhealthy_supplier_is_a_failure() -> None:
    status, error = task_runs.outcome_of(
        {"status": "unhealthy", "message": "401 Unauthorized"}
    )
    assert status == task_runs.STATUS_FAILED and error == "401 Unauthorized"


def test_the_one_article_icecat_task_is_not_journaled() -> None:
    from app.core.arq_worker import WorkerSettings

    by_name = {
        getattr(f, "name", getattr(f, "__name__", "")): f
        for f in WorkerSettings.functions
    }
    single = by_name["enrich_product_with_icecat_task"]
    batch = by_name["batch_enrich_products_task"]
    # Journaled functions are wrapped (functools.wraps sets __wrapped__).
    assert not hasattr(getattr(single, "coroutine", single), "__wrapped__")
    assert hasattr(getattr(batch, "coroutine", batch), "__wrapped__")
