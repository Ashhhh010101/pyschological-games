"""Per-room locks for local and distributed command serialization."""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import AsyncIterator, Awaitable
from contextlib import asynccontextmanager
from typing import Any, cast

from redis.asyncio import Redis
from redis.exceptions import LockError

from backend.domain.exceptions import ConcurrentMutation


class MemoryLockManager:
    def __init__(self) -> None:
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        async with self._guard:
            lock = self._locks.setdefault(key, asyncio.Lock())
        async with lock:
            yield

    async def close(self) -> None:
        self._locks.clear()


class RedisLockManager:
    def __init__(self, url: str, prefix: str, timeout_seconds: int, wait_seconds: int) -> None:
        self.client: Redis = Redis.from_url(url, decode_responses=True)
        self.prefix = prefix
        self.timeout_seconds = timeout_seconds
        self.wait_seconds = wait_seconds

    @asynccontextmanager
    async def hold(self, key: str) -> AsyncIterator[None]:
        lock = self.client.lock(
            f"{self.prefix}:lock:room:{key}",
            timeout=self.timeout_seconds,
            blocking_timeout=self.wait_seconds,
        )
        acquired = bool(await cast(Awaitable[Any], lock.acquire()))
        if not acquired:
            raise ConcurrentMutation("The room is busy; retry with the same idempotency key.")
        try:
            yield
        finally:
            # The lease may have expired; SQL row locking still guards correctness.
            with contextlib.suppress(LockError):
                await cast(Awaitable[Any], lock.release())

    async def close(self) -> None:
        await self.client.aclose()
