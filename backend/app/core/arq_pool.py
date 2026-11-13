# app/core/arq_pool.py
from arq import create_pool
from arq.connections import RedisSettings

from app.core.config import settings


async def get_arq_pool():  # type: ignore[no-untyped-def]
    """Get arq pool (same DSN as the rest of the app, password included)."""
    return await create_pool(RedisSettings.from_dsn(str(settings.REDIS_URL)))
