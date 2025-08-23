# app/core/arq_pool.py
from arq import create_pool
from arq.connections import RedisSettings
import os

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

async def get_arq_pool():
    return await create_pool(RedisSettings.from_dsn(REDIS_URL))
