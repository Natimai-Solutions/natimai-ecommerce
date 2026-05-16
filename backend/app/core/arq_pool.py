# app/core/arq_pool.py
import os

from arq import create_pool
from arq.connections import RedisSettings

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")


async def get_arq_pool():  # type: ignore[no-untyped-def]
    """Get arq pool."""
    return await create_pool(RedisSettings.from_dsn(REDIS_URL))
