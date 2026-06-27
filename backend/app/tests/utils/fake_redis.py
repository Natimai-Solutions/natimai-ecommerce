"""A tiny in-memory async Redis stub for the OTP-signup tests.

Implements only the operations the OTP service uses (incr/expire/set/get/ttl/
delete/getdel) and stores values as bytes, like a real redis client without
``decode_responses``. TTLs are recorded but not time-enforced — the OTP logic
under test depends on counters/attempts, not on wall-clock expiry.
"""

from __future__ import annotations

from typing import Any


class FakeRedis:
    """Minimal async Redis double (bytes values, no real expiry)."""

    def __init__(self) -> None:
        self._store: dict[str, bytes] = {}
        self._ttl: dict[str, int] = {}

    @staticmethod
    def _b(value: str | bytes) -> bytes:
        return value.encode() if isinstance(value, str) else value

    async def incr(self, key: str) -> int:
        value = int(self._store.get(key, b"0")) + 1
        self._store[key] = str(value).encode()
        return value

    async def expire(self, key: str, ttl: int) -> None:
        self._ttl[key] = ttl

    async def set(self, key: str, value: str | bytes, ex: int | None = None) -> None:
        self._store[key] = self._b(value)
        if ex is not None:
            self._ttl[key] = ex

    async def get(self, key: str) -> bytes | None:
        return self._store.get(key)

    async def ttl(self, key: str) -> int:
        return self._ttl.get(key, -1)

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)
        self._ttl.pop(key, None)

    async def getdel(self, key: str) -> bytes | None:
        self._ttl.pop(key, None)
        return self._store.pop(key, None)


def fake_redis() -> Any:
    """A FakeRedis typed as ``Any`` so it satisfies ``redis.Redis`` parameters."""
    return FakeRedis()
