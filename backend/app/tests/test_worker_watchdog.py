"""The worker ends itself when stuck so Docker restarts it (Z3, decision of
18/11/2026)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from app.core import worker_watchdog as wd


def test_a_fresh_worker_is_fine() -> None:
    state = wd.WatchdogState()
    assert wd.stuck_reason(state, time.monotonic()) is None


def test_a_blocked_loop_or_a_lost_redis_is_stuck() -> None:
    now = time.monotonic()
    blocked = wd.WatchdogState(last_beat=now - 400, last_redis_ok=now)
    assert "event loop blocked" in (wd.stuck_reason(blocked, now) or "")
    no_redis = wd.WatchdogState(last_beat=now, last_redis_ok=now - 200)
    assert "Redis unreachable" in (wd.stuck_reason(no_redis, now) or "")


def test_the_watch_exits_the_process_when_stuck(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wd, "CHECK_SECONDS", 0.01)
    state = wd.WatchdogState(last_beat=time.monotonic() - 1000)
    exits: list[bool] = []
    wd._watch(state, exit_process=lambda: exits.append(True))
    assert exits == [True]


@pytest.mark.asyncio
async def test_the_loop_keeps_the_heartbeat_and_the_ping_fresh(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(wd, "BEAT_SECONDS", 0.01)
    monkeypatch.setattr(wd, "PING_SECONDS", 0.01)
    monkeypatch.setattr(wd, "CHECK_SECONDS", 60)

    class Redis:
        async def ping(self) -> bool:
            return True

    ctx: dict[str, Any] = {"redis": Redis()}
    await wd.start_watchdog(ctx)
    state = ctx["watchdog"]
    state.last_beat = state.last_redis_ok = 0.0
    await asyncio.sleep(0.05)
    assert state.last_beat > 0 and state.last_redis_ok > 0
    await wd.stop_watchdog(ctx)
    assert state.stop.is_set()


@pytest.mark.asyncio
async def test_it_can_be_switched_off(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WORKER_WATCHDOG", "0")
    ctx: dict[str, Any] = {}
    await wd.start_watchdog(ctx)
    assert "watchdog" not in ctx
