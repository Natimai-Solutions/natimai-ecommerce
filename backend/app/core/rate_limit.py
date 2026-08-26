"""Redis-backed rate limiting (fixed window) + proxy-aware client IP.

Redis is the natural backend here: it is already in the stack (ARQ broker)
and, unlike an in-memory counter, survives multi-replica deployments (cf. the
B7 lesson on ``CheckoutMetricsStore``).

Fail-open by design: if Redis is unreachable the request is allowed and a
warning is logged — an outage must not lock every customer out of login.
"""

from __future__ import annotations

import logging

import redis.asyncio as redis
from fastapi import Request

from app.core.config import settings

logger = logging.getLogger(__name__)

_client: redis.Redis | None = None


def _get_client() -> redis.Redis:
    """Shared lazy client (its connection pool handles concurrency)."""
    global _client
    if _client is None:
        _client = redis.from_url(  # type: ignore[no-untyped-call]
            str(settings.REDIS_URL),
            socket_connect_timeout=1,
            socket_timeout=1,
        )
    return _client


async def hit_rate_limit(key: str, *, limit: int, window_seconds: int) -> bool:
    """Register a hit on ``key`` and tell whether the caller is over the limit.

    Fixed-window counter: INCR + EXPIRE on first hit. Returns True when the
    number of hits within the window exceeds ``limit``; False otherwise or
    when Redis is unavailable (fail-open).
    """
    redis_key = f"rate:{key}"
    try:
        client = _get_client()
        count = await client.incr(redis_key)
        if count == 1:
            await client.expire(redis_key, window_seconds)
        return int(count) > limit
    except Exception:  # noqa: BLE001 — any Redis failure must fail open
        logger.warning("rate limiter unavailable, allowing request", exc_info=True)
        return False


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
