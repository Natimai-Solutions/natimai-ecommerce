import aioredis

from app.core.config import settings


class RedisCache:
    def __init__(self):
        self.cache = None

    async def __aenter__(self) -> aioredis.Redis:
        self.cache = await aioredis.from_url(settings.REDIS_URL)
        return self.cache

    async def __aexit__(self, exc_type, exc, tb):
        await self.cache.close()
