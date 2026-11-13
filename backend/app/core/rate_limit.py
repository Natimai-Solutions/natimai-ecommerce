"""Redis-backed rate limiting (fixed window) + proxy-aware client IP.

Redis is the natural backend here: it is already in the stack (ARQ broker)
and, unlike an in-memory counter, survives multi-replica deployments (cf. the
B7 lesson on ``CheckoutMetricsStore``).

Fail-closed: if Redis is unreachable the protected route answers 503
(``rate_limit.unavailable``) instead of letting the request through. A login,
a code check or a gift-card redeem without a limit is worse than a minute of
unavailability — and Redis can be pushed over on purpose to lift the limits.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import Awaitable, Callable

import redis.asyncio as redis
from fastapi import Request

from app.core.config import settings
from app.core.errors import AppError

logger = logging.getLogger(__name__)

_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, redis.Redis] = (
    weakref.WeakKeyDictionary()
)


def _get_client() -> redis.Redis:
    """Shared lazy client of the running event loop (its connection pool
    handles concurrency). A pool is bound to the loop that opened it: a
    process running several loops (the test client, a script) gets one each,
    instead of a client whose every call fails on the wrong loop."""
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client = redis.from_url(  # type: ignore[no-untyped-call]
            str(settings.REDIS_URL),
            socket_connect_timeout=1,
            socket_timeout=1,
        )
        _clients[loop] = client
    return client


def shared_redis() -> redis.Redis:
    """The Redis client of this event loop, for other small shared counters."""
    return _get_client()


async def hit_rate_limit(key: str, *, limit: int, window_seconds: int) -> bool:
    """Register a hit on ``key`` and tell whether the caller is over the limit.

    Fixed-window counter: INCR and EXPIRE NX in one transaction (a counter
    never outlives its window). Returns True when the number of hits within
    the window exceeds ``limit``. Raises ``rate_limit.unavailable`` (503)
    when Redis does not answer: no limit means no access (fail-closed).
    """
    redis_key = f"rate:{key}"
    try:
        async with _get_client().pipeline(transaction=True) as pipe:
            pipe.incr(redis_key)
            pipe.expire(redis_key, window_seconds, nx=True)
            count, _ = await pipe.execute()
    except Exception as exc:  # noqa: BLE001 — any Redis failure closes the route
        logger.error("rate limiter unavailable, refusing request", exc_info=True)
        raise AppError(
            code="rate_limit.unavailable",
            status_code=503,
            message="Service momentanément indisponible : réessayez dans un instant.",
            details={},
        ) from exc
    return int(count) > limit


async def rate_limit_reached(key: str, *, limit: int) -> bool:
    """Whether ``key`` already counts more than ``limit`` hits, without adding
    one. For limits that only count failures (see ``hit_rate_limit``): read
    before the attempt, hit after a failure. Fail-closed like the hit."""
    try:
        raw = await _get_client().get(f"rate:{key}")
    except Exception as exc:  # noqa: BLE001 — any Redis failure closes the route
        logger.error("rate limiter unavailable, refusing request", exc_info=True)
        raise AppError(
            code="rate_limit.unavailable",
            status_code=503,
            message="Service momentanément indisponible : réessayez dans un instant.",
            details={},
        ) from exc
    return raw is not None and int(raw) >= limit


def rate_limited(
    scope: str, *, limit: int, window_seconds: int
) -> Callable[[Request], Awaitable[None]]:
    """FastAPI dependency: at most ``limit`` calls per client IP and window
    on the routes that carry it (R8 / U5). Over the limit → ``AppError``
    ``<scope>.rate_limited`` (429, ``Retry-After``-free); 503 when Redis is down.
    """

    async def dependency(request: Request) -> None:
        ip = get_client_ip(request)
        if await hit_rate_limit(
            f"{scope}:{ip}", limit=limit, window_seconds=window_seconds
        ):
            raise AppError(
                code=f"{scope}.rate_limited",
                status_code=429,
                message="Trop de tentatives : réessayez dans quelques minutes.",
                details={"scope": scope, "window_seconds": window_seconds},
            )

    return dependency


def get_client_ip(request: Request) -> str:
    """Real client IP, proxy-aware.

    When ``CLIENT_IP_HEADER`` is configured (Cloudflare / reverse proxy in
    front), that header wins. For an ``X-Forwarded-For`` chain the **last**
    entry is used: it is the one appended by our own proxy (Caddy/nginx append
    the peer address), while earlier entries are client-supplied and forgeable
    — taking the first would let a client bypass the per-IP login throttle
    with an arbitrary header. Single-value headers written by the edge
    (``CF-Connecting-IP``) are unaffected. Otherwise the socket peer address
    is used; never trust forwarded headers when directly exposed (spoofable).
    """
    header_name = settings.CLIENT_IP_HEADER
    if header_name:
        raw = request.headers.get(header_name)
        if raw:
            return raw.split(",")[-1].strip()
    return request.client.host if request.client else "unknown"
