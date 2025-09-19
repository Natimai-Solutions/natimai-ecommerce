import redis.asyncio as redis

from app.core.config import settings


class RedisCache:
    def __init__(self):
        self.cache = None

    async def __aenter__(self) -> redis.Redis:
        self.cache = redis.from_url(str(settings.REDIS_URL))
        return self.cache

    async def __aexit__(self, exc_type, exc, tb):
        await self.cache.aclose()
