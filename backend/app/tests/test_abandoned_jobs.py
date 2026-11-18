"""Jobs arq gives up on before running them are journaled and alerted
(review of 17/11/2026: « État du système » kept such a task « ok »)."""

from __future__ import annotations

from typing import Any

import pytest
from arq.jobs import serialize_result
from arq.worker import JobExecutionFailed, Worker

from app.core import task_runs


@pytest.mark.asyncio
async def test_a_job_past_its_tries_before_running_is_recorded(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    finished: list[str] = []
    recorded: list[tuple[str, str, str | None]] = []

    async def original(_self: Any, job_id: str, _data: bytes | None) -> None:
        finished.append(job_id)

    async def record(name: str, status: str, error: str | None = None, *_: Any) -> None:
        recorded.append((name, status, error))

    monkeypatch.setattr(Worker, "finish_failed_job", original)
    monkeypatch.setattr(task_runs, "record_run", record)
    task_runs.install_abandoned_job_journal()
    task_runs.install_abandoned_job_journal()  # idempotent

    data = serialize_result(
        "sync_supplier_inventory_task",
        (),
        {"supplier_name": "ingram"},
        6,
        0,
        False,
        JobExecutionFailed("max 5 retries exceeded"),
        0,
        1,
        "job-1:sync_supplier_inventory_task",
        "arq:queue",
        job_id="job-1",
    )
    await Worker.finish_failed_job(object(), "job-1", data)  # type: ignore[arg-type]

    assert finished == ["job-1"]
    assert len(recorded) == 1
    name, status, error = recorded[0]
    assert name == "sync_supplier_inventory_task:ingram"
    assert status == task_runs.STATUS_FAILED
    assert error is not None and "max 5 retries exceeded" in error
