"""Fixed-window rate limiting with interchangeable memory and Redis stores."""

from __future__ import annotations

import asyncio
import re
import time
from collections.abc import Awaitable
from typing import Any, cast

from redis.asyncio import Redis

from backend.domain.exceptions import RateLimitExceeded

_LIMIT = re.compile(r"^(?P<count>[1-9]\d*)\s*/\s*(?P<unit>second|minute|hour)s?$", re.IGNORECASE)
_SECONDS = {"second": 1, "minute": 60, "hour": 3600}
_INCREMENT = """
local current = redis.call('INCR', KEYS[1])
if current == 1 then redis.call('EXPIRE', KEYS[1], ARGV[1]) end
return current
"""


def parse_limit(value: str) -> tuple[int, int]:
    match = _LIMIT.fullmatch(value.strip())
    if match is None:
        raise ValueError(f"Invalid rate limit: {value}")
    return int(match.group("count")), _SECONDS[match.group("unit").lower()]


class MemoryRateLimiter:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self._windows: dict[str, tuple[int, float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, scope: str, identity: str, limit: str) -> None:
        if not self.enabled:
            return
        maximum, window = parse_limit(limit)
        key = f"{scope}:{identity}"
        now = time.monotonic()
        async with self._lock:
            count, expires_at = self._windows.get(key, (0, now + window))
            if expires_at <= now:
                count, expires_at = 0, now + window
            count += 1
            self._windows[key] = (count, expires_at)
        if count > maximum:
            raise RateLimitExceeded("Too many requests. Try again after the current rate-limit window.")

    async def close(self) -> None:
        self._windows.clear()


class RedisRateLimiter:
    def __init__(self, url: str, prefix: str, enabled: bool = True) -> None:
        self.client: Redis = Redis.from_url(url, decode_responses=True)
        self.prefix = prefix
        self.enabled = enabled

    async def check(self, scope: str, identity: str, limit: str) -> None:
        if not self.enabled:
            return
        maximum, window = parse_limit(limit)
        bucket = int(time.time()) // window
        key = f"{self.prefix}:rate:{scope}:{identity}:{bucket}"
        pending = cast(Awaitable[Any], self.client.eval(_INCREMENT, 1, key, str(window)))
        count = int(await pending)
        if count > maximum:
            raise RateLimitExceeded("Too many requests. Try again after the current rate-limit window.")

    async def close(self) -> None:
        await self.client.aclose()
