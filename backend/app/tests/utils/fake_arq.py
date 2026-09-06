"""An in-memory stand-in for the ARQ Redis pool used by ``enqueue_with_dedup``.

Records every enqueued job so tests can assert *what* was queued (function,
job kwargs) without a Redis server. ``set(..., nx=True)`` honours the
dedup semantics: a second identical trigger within the window is absorbed.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any


class FakeArqRedis:
    """Minimal async double of the arq Redis pool (set/get/enqueue_job)."""

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.jobs: list[dict[str, Any]] = []

    async def set(
        self,
        key: str,
        value: str | bytes,
        ex: int | None = None,
        nx: bool = False,
    ) -> bool:
        if nx and key in self.store:
            return False
        self.store[key] = value.encode() if isinstance(value, str) else value
        return True

    async def get(self, key: str) -> bytes | None:
        return self.store.get(key)

    async def enqueue_job(
        self, function: str, *, _job_id: str | None = None, **kwargs: Any
    ) -> Any:
        job_id = _job_id or f"job_{len(self.jobs)}"
        self.jobs.append({"function": function, "job_id": job_id, **kwargs})
        return SimpleNamespace(job_id=job_id)

    def jobs_for(self, function: str) -> list[dict[str, Any]]:
        return [job for job in self.jobs if job["function"] == function]
