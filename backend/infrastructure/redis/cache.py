"""TTL cache implementations for local development and Redis deployments."""

from __future__ import annotations

import asyncio
import time

from redis.asyncio import Redis


class MemoryCache:
    def __init__(self) -> None:
        self._values: dict[str, tuple[str, float]] = {}
        self._lock = asyncio.Lock()

    async def get(self, key: str) -> str | None:
        async with self._lock:
            entry = self._values.get(key)
            if entry is None:
                return None
            value, expires_at = entry
            if expires_at <= time.monotonic():
                self._values.pop(key, None)
                return None
            return value

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        async with self._lock:
            self._values[key] = (value, time.monotonic() + ttl_seconds)

    async def delete(self, key: str) -> None:
        async with self._lock:
            self._values.pop(key, None)

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        self._values.clear()


class RedisCache:
    def __init__(self, url: str, prefix: str) -> None:
        self.client: Redis = Redis.from_url(url, decode_responses=True)
        self.prefix = prefix

    def _key(self, key: str) -> str:
        return f"{self.prefix}:{key}"

    async def get(self, key: str) -> str | None:
        value = await self.client.get(self._key(key))
        return str(value) if value is not None else None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        await self.client.set(self._key(key), value, ex=ttl_seconds)

    async def delete(self, key: str) -> None:
        await self.client.delete(self._key(key))

    async def ready(self) -> bool:
        try:
            return bool(await self.client.ping())
        except Exception:
            return False

    async def close(self) -> None:
        await self.client.aclose()
