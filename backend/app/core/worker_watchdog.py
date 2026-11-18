"""The worker ends itself when it is stuck, so Docker starts a fresh one.

Docker restarts a container whose process exits (``restart: unless-stopped``)
but not one that is merely « unhealthy »: a worker whose event loop is
blocked, or that lost Redis for good, kept running and did nothing while the
healthcheck said so (functional audit, November 2026, Z3 — decision of
18/11/2026: watchdog in the worker + a cron on the server).

Two signals, both written from the worker's event loop:

* a heartbeat every :data:`BEAT_SECONDS` — stale means the loop is blocked;
* a Redis ping every :data:`PING_SECONDS` — failing for long means the worker
  cannot take or finish a job.

A separate thread reads them: past :data:`LOOP_STALL_SECONDS` or
:data:`REDIS_DOWN_SECONDS` it logs and exits the process (``os._exit``: a
blocked loop would never run a clean shutdown). The jobs that were running
are retried by arq (``max_tries``). A process frozen as a whole stops the
thread too; the server-side cron (``scripts/ops/restart-unhealthy.sh``)
covers that case from the healthcheck.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

BEAT_SECONDS = 5
PING_SECONDS = 20
CHECK_SECONDS = 15
#: A job may block the loop a while (a PDF, a big file); five minutes is not
#: a job any more.
LOOP_STALL_SECONDS = 300
REDIS_DOWN_SECONDS = 180


@dataclass
class WatchdogState:
    last_beat: float = field(default_factory=time.monotonic)
    last_redis_ok: float = field(default_factory=time.monotonic)
    stop: threading.Event = field(default_factory=threading.Event)
    tasks: list[asyncio.Task[None]] = field(default_factory=list)


def stuck_reason(
    state: WatchdogState,
    now: float,
    *,
    loop_stall: float = LOOP_STALL_SECONDS,
    redis_down: float = REDIS_DOWN_SECONDS,
) -> str | None:
    """Why the worker must restart, or None while it is fine."""
    if now - state.last_beat > loop_stall:
        return f"event loop blocked for {int(now - state.last_beat)} s"
    if now - state.last_redis_ok > redis_down:
        return f"Redis unreachable for {int(now - state.last_redis_ok)} s"
    return None


def _exit_process() -> None:  # pragma: no cover - ends the process
    os._exit(1)


def _watch(
    state: WatchdogState, exit_process: Callable[[], None] = _exit_process
) -> None:
    while not state.stop.wait(CHECK_SECONDS):
        reason = stuck_reason(state, time.monotonic())
        if reason:
            logger.critical("Worker watchdog: %s — exiting for a restart", reason)
            exit_process()
            return


async def _beat(state: WatchdogState) -> None:
    while True:
        state.last_beat = time.monotonic()
        await asyncio.sleep(BEAT_SECONDS)


async def _ping(state: WatchdogState, redis: Any) -> None:
    while True:
        try:
            await asyncio.wait_for(redis.ping(), timeout=10)
            state.last_redis_ok = time.monotonic()
        except Exception:  # noqa: BLE001 - counted by the watch thread
            logger.warning("Worker watchdog: Redis ping failed", exc_info=True)
        await asyncio.sleep(PING_SECONDS)


async def start_watchdog(ctx: dict[str, Any]) -> None:
    """arq ``on_startup``: start the heartbeat, the ping and the watch."""
    if os.environ.get("WORKER_WATCHDOG", "1").strip().lower() in {"0", "false", "off"}:
        logger.info("Worker watchdog switched off (WORKER_WATCHDOG)")
        return
    state = WatchdogState()
    state.tasks.append(asyncio.create_task(_beat(state)))
    if ctx.get("redis") is not None:
        state.tasks.append(asyncio.create_task(_ping(state, ctx["redis"])))
    threading.Thread(
        target=_watch, args=(state,), name="worker-watchdog", daemon=True
    ).start()
    ctx["watchdog"] = state


async def stop_watchdog(ctx: dict[str, Any]) -> None:
    """arq ``on_shutdown``: a clean stop is not a stuck worker."""
    state = ctx.get("watchdog")
    if not isinstance(state, WatchdogState):
        return
    state.stop.set()
    for task in state.tasks:
        task.cancel()
