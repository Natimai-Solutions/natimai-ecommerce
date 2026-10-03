"""Client-side throttling and retry for outbound supplier HTTP calls.

Both the Ingram and Icecat clients used to raise a bare ``Exception`` on any
non-200 status. A single HTTP 429 in the middle of a catalog page therefore
lost the whole category, and the ARQ job retry re-hammered the same endpoint
immediately — the worst possible response to being told to slow down.

Two mechanisms live here:

``AsyncRateLimiter``
    A soft, in-process floor on the interval between two requests, derived
    from the ``requests_per_minute`` hint the supplier adapters already
    declared but nobody ever read. It only smooths *our own* burst; it makes
    no claim about what the remote actually allows.

``request_with_retry``
    Exponential backoff with jitter around a single attempt, honouring the
    ``Retry-After`` header when the server sends one. Transient statuses
    (429 and 5xx) and connection errors are retried; everything else is
    surfaced immediately, because retrying a 400 or a 403 only wastes quota.

Exhausting the attempts re-raises, so the ARQ job retry stays the outer
safety net — this layer just stops it being the *first* one.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from collections.abc import Awaitable, Callable
from typing import TypeVar

import aiohttp

logger = logging.getLogger(__name__)

T = TypeVar("T")

#: Statuses worth trying again: rate limiting and transient server faults.
#: 501/505 are excluded on purpose — they will not change on a retry.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

#: Never sleep longer than this on a single attempt, whatever ``Retry-After``
#: claims: an ARQ job has a 600 s timeout, and a supplier answering
#: "come back in an hour" should fail the run so the next cron picks it up.
MAX_BACKOFF_SECONDS = 120.0


class RetryableHTTPError(Exception):
    """A response that is worth retrying, raised by the per-attempt callable.

    ``retry_after`` carries the server's own instruction (in seconds) when it
    sent one; the backoff prefers it over its own computed delay.
    """

    def __init__(
        self,
        status: int,
        message: str = "",
        retry_after: float | None = None,
    ) -> None:
        """Initialise the error with the offending status and optional hint."""
        self.status = status
        self.retry_after = retry_after
        super().__init__(message or f"retryable HTTP status {status}")


def parse_retry_after(value: str | None) -> float | None:
    """Read a ``Retry-After`` header expressed in seconds.

    The HTTP-date form is deliberately not supported: suppliers send the
    delta-seconds form, and a mis-parsed date would produce a nonsense sleep.
    An unparseable value simply falls back to the computed backoff.
    """
    if not value:
        return None
    try:
        seconds = float(value.strip())
    except (TypeError, ValueError):
        return None
    return seconds if seconds >= 0 else None


def backoff_delay(attempt: int, *, base_delay: float, max_delay: float) -> float:
    """Return the delay before ``attempt`` (1-based), with full jitter.

    Full jitter (a uniform draw in ``[0, computed]``) rather than a fixed
    exponential: several workers throttled at the same instant must not come
    back in lockstep and re-trigger the same 429.
    """
    ceiling = min(base_delay * (2 ** (attempt - 1)), max_delay)
    return random.uniform(0, ceiling)  # noqa: S311 - jitter, not cryptography


class AsyncRateLimiter:
    """Serialise callers so requests keep a minimum interval between them.

    In-process only: with several workers each keeps its own budget. It is a
    politeness floor, not a distributed quota.
    """

    def __init__(self, requests_per_minute: int | None) -> None:
        """Build a limiter; ``None`` or a non-positive rate disables it."""
        self._min_interval = (
            60.0 / requests_per_minute
            if requests_per_minute and requests_per_minute > 0
            else 0.0
        )
        self._lock = asyncio.Lock()
        self._next_allowed_at = 0.0

    @property
    def enabled(self) -> bool:
        """Return ``True`` when a positive rate was configured."""
        return self._min_interval > 0

    async def acquire(self) -> None:
        """Wait until the next request is allowed to leave."""
        if not self.enabled:
            return
        async with self._lock:
            now = time.monotonic()
            wait_for = self._next_allowed_at - now
            if wait_for > 0:
                await asyncio.sleep(wait_for)
                now = time.monotonic()
            self._next_allowed_at = now + self._min_interval


async def request_with_retry(
    attempt: Callable[[], Awaitable[T]],
    *,
    description: str,
    max_attempts: int = 4,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    rate_limiter: AsyncRateLimiter | None = None,
    retry_connection_errors: bool = True,
) -> T:
    """Run ``attempt`` until it succeeds, gives up, or raises a fatal error.

    ``attempt`` performs exactly one HTTP call and raises
    :class:`RetryableHTTPError` for a status worth trying again. Any other
    exception is fatal and propagates untouched on the first occurrence.

    ``retry_connection_errors`` must be turned off for non-idempotent calls.
    A dropped connection on a POST is ambiguous — the server may well have
    processed it — so replaying a purchase order on a timeout could place it
    twice. A 429 carries no such ambiguity: the request was refused, never
    executed, and is always safe to replay.
    """
    last_error: Exception | None = None

    for attempt_number in range(1, max_attempts + 1):
        if rate_limiter is not None:
            await rate_limiter.acquire()
        try:
            return await attempt()
        except RetryableHTTPError as exc:
            last_error = exc
            hinted = exc.retry_after
            delay = (
                min(hinted, MAX_BACKOFF_SECONDS)
                if hinted is not None
                else backoff_delay(
                    attempt_number, base_delay=base_delay, max_delay=max_delay
                )
            )
        except (TimeoutError, aiohttp.ClientError) as exc:
            if not retry_connection_errors:
                raise
            last_error = exc
            delay = backoff_delay(
                attempt_number, base_delay=base_delay, max_delay=max_delay
            )

        if attempt_number == max_attempts:
            break

        logger.warning(
            "%s failed (attempt %d/%d): %s — retrying in %.1fs",
            description,
            attempt_number,
            max_attempts,
            last_error,
            delay,
        )
        await asyncio.sleep(delay)

    logger.error(
        "%s gave up after %d attempts: %s", description, max_attempts, last_error
    )
    assert last_error is not None  # noqa: S101 - loop always sets it before break
    raise last_error
