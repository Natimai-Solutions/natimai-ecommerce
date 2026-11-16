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
