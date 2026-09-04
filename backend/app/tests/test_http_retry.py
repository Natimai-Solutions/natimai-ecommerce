"""Backoff and throttling of outbound supplier calls (``app.core.http_retry``).

Before this layer existed a single HTTP 429 raised a bare ``Exception``, the
catalog page was lost, and the ARQ job retry re-sent the same request at once.
"""

from __future__ import annotations

import asyncio

import aiohttp
import pytest

from app.core.http_retry import (
    MAX_BACKOFF_SECONDS,
    RETRYABLE_STATUSES,
    AsyncRateLimiter,
    RetryableHTTPError,
    backoff_delay,
    parse_retry_after,
    request_with_retry,
)


@pytest.fixture(autouse=True)
def _no_real_sleeping(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Record backoff sleeps instead of serving them, and keep tests instant."""
    slept: list[float] = []

    async def _fake_sleep(delay: float) -> None:
        slept.append(delay)

    monkeypatch.setattr(asyncio, "sleep", _fake_sleep)
    return slept


# -- Retry-After parsing ----------------------------------------------------


def test_parse_retry_after_reads_delta_seconds() -> None:
    assert parse_retry_after("30") == 30.0
    assert parse_retry_after(" 2.5 ") == 2.5


def test_parse_retry_after_rejects_unusable_values() -> None:
    """An HTTP-date or garbage must fall back to the computed backoff."""
    assert parse_retry_after(None) is None
    assert parse_retry_after("") is None
    assert parse_retry_after("Wed, 21 Oct 2026 07:28:00 GMT") is None
    assert parse_retry_after("-5") is None


# -- backoff ----------------------------------------------------------------


def test_backoff_grows_and_stays_under_the_ceiling() -> None:
    for attempt in range(1, 8):
        delay = backoff_delay(attempt, base_delay=1.0, max_delay=30.0)
        assert 0.0 <= delay <= 30.0


def test_backoff_is_jittered_not_lockstep() -> None:
    """Two workers throttled together must not come back at the same instant."""
    draws = {backoff_delay(4, base_delay=1.0, max_delay=30.0) for _ in range(50)}
    assert len(draws) > 1


# -- request_with_retry -----------------------------------------------------


@pytest.mark.asyncio
async def test_returns_first_success_without_sleeping(
    _no_real_sleeping: list[float],
) -> None:
    async def attempt() -> str:
        return "payload"

    assert await request_with_retry(attempt, description="test") == "payload"
    assert _no_real_sleeping == []


@pytest.mark.asyncio
async def test_retries_a_429_then_succeeds(_no_real_sleeping: list[float]) -> None:
    calls: list[int] = []

    async def attempt() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise RetryableHTTPError(429, "throttled")
        return "payload"

    assert await request_with_retry(attempt, description="test") == "payload"
    assert len(calls) == 3
    assert len(_no_real_sleeping) == 2


@pytest.mark.asyncio
async def test_honours_retry_after_over_computed_backoff(
    _no_real_sleeping: list[float],
) -> None:
    async def attempt() -> str:
        raise RetryableHTTPError(429, "throttled", retry_after=7.0)

    with pytest.raises(RetryableHTTPError):
        await request_with_retry(attempt, description="test", max_attempts=2)

    assert _no_real_sleeping == [7.0]


@pytest.mark.asyncio
async def test_caps_an_absurd_retry_after(_no_real_sleeping: list[float]) -> None:
    """ "Come back in an hour" must fail the run, not pin the ARQ job."""

    async def attempt() -> str:
        raise RetryableHTTPError(429, "throttled", retry_after=3600.0)

    with pytest.raises(RetryableHTTPError):
        await request_with_retry(attempt, description="test", max_attempts=2)

    assert _no_real_sleeping == [MAX_BACKOFF_SECONDS]


@pytest.mark.asyncio
async def test_gives_up_after_max_attempts_and_reraises(
    _no_real_sleeping: list[float],
) -> None:
    calls: list[int] = []

    async def attempt() -> str:
        calls.append(1)
        raise RetryableHTTPError(503, "unavailable")

    with pytest.raises(RetryableHTTPError) as excinfo:
        await request_with_retry(attempt, description="test", max_attempts=4)

    assert len(calls) == 4
    assert len(_no_real_sleeping) == 3  # no sleep after the final attempt
    assert excinfo.value.status == 503


@pytest.mark.asyncio
async def test_a_fatal_status_is_not_retried(_no_real_sleeping: list[float]) -> None:
    """Replaying a 400 or a 403 only burns quota."""
    calls: list[int] = []

    async def attempt() -> str:
        calls.append(1)
        raise ValueError("400 Bad Request")

    with pytest.raises(ValueError):
        await request_with_retry(attempt, description="test")

    assert len(calls) == 1
    assert _no_real_sleeping == []


@pytest.mark.asyncio
async def test_connection_errors_are_retried_by_default(
    _no_real_sleeping: list[float],
) -> None:
    calls: list[int] = []

    async def attempt() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise aiohttp.ClientConnectionError("reset by peer")
        return "payload"

    assert await request_with_retry(attempt, description="test") == "payload"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_connection_errors_are_not_replayed_for_writes(
    _no_real_sleeping: list[float],
) -> None:
    """A dropped POST may have been executed — placing an order twice costs money."""
    calls: list[int] = []

    async def attempt() -> str:
        calls.append(1)
        raise aiohttp.ClientConnectionError("reset by peer")

    with pytest.raises(aiohttp.ClientConnectionError):
        await request_with_retry(
            attempt, description="test", retry_connection_errors=False
        )

    assert len(calls) == 1
    assert _no_real_sleeping == []


@pytest.mark.asyncio
async def test_timeouts_are_retried(_no_real_sleeping: list[float]) -> None:
    calls: list[int] = []

    async def attempt() -> str:
        calls.append(1)
        if len(calls) < 2:
            raise asyncio.TimeoutError
        return "payload"

    assert await request_with_retry(attempt, description="test") == "payload"
    assert len(calls) == 2


@pytest.mark.asyncio
async def test_rate_limiter_is_acquired_before_every_attempt(
    _no_real_sleeping: list[float],
) -> None:
    acquired: list[int] = []

    class _SpyLimiter(AsyncRateLimiter):
        async def acquire(self) -> None:
            acquired.append(1)

    calls: list[int] = []

    async def attempt() -> str:
        calls.append(1)
        if len(calls) < 3:
            raise RetryableHTTPError(429)
        return "payload"

    await request_with_retry(attempt, description="test", rate_limiter=_SpyLimiter(60))

    assert len(acquired) == 3


# -- retryable status set ---------------------------------------------------


def test_retryable_statuses_cover_throttling_and_transient_faults() -> None:
    assert 429 in RETRYABLE_STATUSES
    assert {500, 502, 503, 504} <= RETRYABLE_STATUSES
    # A retry would return the same answer for these.
    assert 400 not in RETRYABLE_STATUSES
    assert 401 not in RETRYABLE_STATUSES
    assert 403 not in RETRYABLE_STATUSES
    assert 404 not in RETRYABLE_STATUSES


# -- AsyncRateLimiter -------------------------------------------------------


def test_rate_limiter_disabled_without_a_rate() -> None:
    assert AsyncRateLimiter(None).enabled is False
    assert AsyncRateLimiter(0).enabled is False
    assert AsyncRateLimiter(-1).enabled is False
    assert AsyncRateLimiter(60).enabled is True


@pytest.mark.asyncio
async def test_disabled_rate_limiter_never_waits(
    _no_real_sleeping: list[float],
) -> None:
    await AsyncRateLimiter(None).acquire()
    assert _no_real_sleeping == []


@pytest.mark.asyncio
async def test_rate_limiter_spaces_out_consecutive_calls(
    monkeypatch: pytest.MonkeyPatch, _no_real_sleeping: list[float]
) -> None:
    """60 requests/minute means the second call waits about a second."""
    clock = {"now": 1000.0}
    monkeypatch.setattr(
        "app.core.http_retry.time", type("_C", (), {"monotonic": lambda: clock["now"]})
    )

    limiter = AsyncRateLimiter(60)
    await limiter.acquire()  # first call goes straight through
    assert _no_real_sleeping == []

    await limiter.acquire()
    assert _no_real_sleeping == [pytest.approx(1.0)]
