import redis.asyncio as redis

from app.core.config import settings


class RedisCache:
    def __init__(self) -> None:
        self.cache: redis.Redis | None = None

    async def __aenter__(self) -> redis.Redis:
        self.cache = redis.from_url(str(settings.REDIS_URL))  # type: ignore[no-untyped-call]
        return self.cache  # type: ignore[return-value]

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        if self.cache is not None:
            await self.cache.aclose()
