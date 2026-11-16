# app/core/arq_pool.py
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings


def arq_redis_settings() -> RedisSettings:
    """ARQ's connection, built field by field.

    ``RedisSettings.from_dsn(settings.REDIS_URL)`` kept the password
    percent-encoded (arq does not decode it, redis-py does): with a
    ``REDIS_PASSWORD`` holding ``+``, ``/`` or ``=`` the API connected and
    the worker and the outbox poller were refused.
    """
    return RedisSettings(
        host=settings.REDIS_SERVER,
        port=int(settings.REDIS_PORT),
        username=(settings.REDIS_USER or None) if settings.REDIS_PASSWORD else None,
        password=settings.REDIS_PASSWORD or None,
    )


async def get_arq_pool():  # type: ignore[no-untyped-def]
    """Get arq pool (same server and password as the rest of the app)."""
    return await create_pool(arq_redis_settings())
