import asyncio
import unittest

from backend.domain.exceptions import RateLimitExceeded
from backend.infrastructure.redis.cache import MemoryCache
from backend.infrastructure.redis.lock import MemoryLockManager
from backend.infrastructure.redis.pubsub import LocalEventBus
from backend.infrastructure.redis.rate_limit import MemoryRateLimiter, parse_limit


class CoordinationTests(unittest.IsolatedAsyncioTestCase):
    async def test_local_event_bus_delivers_room_versions(self) -> None:
        bus = LocalEventBus()
        received: list[tuple[str, int]] = []

        async def handle(code: str, version: int) -> None:
            received.append((code, version))

        await bus.start(handle)
        await bus.publish("ABCDE", 7)
        self.assertEqual(received, [("ABCDE", 7)])
        await bus.close()

    async def test_memory_cache_supports_ttl_entries_and_deletion(self) -> None:
        cache = MemoryCache()
        await cache.set("room:ABCDE", "7", 60)
        self.assertEqual(await cache.get("room:ABCDE"), "7")
        await cache.delete("room:ABCDE")
        self.assertIsNone(await cache.get("room:ABCDE"))

    async def test_rate_limit_is_scoped_by_identity(self) -> None:
        limiter = MemoryRateLimiter()
        await limiter.check("create", "client-a", "2/minute")
        await limiter.check("create", "client-a", "2/minute")
        await limiter.check("create", "client-b", "2/minute")
        with self.assertRaises(RateLimitExceeded):
            await limiter.check("create", "client-a", "2/minute")
        self.assertEqual(parse_limit("30/hour"), (30, 3600))

    async def test_memory_room_lock_serializes_mutations(self) -> None:
        locks = MemoryLockManager()
        first_acquired = asyncio.Event()
        release_first = asyncio.Event()
        second_acquired = asyncio.Event()

        async def first() -> None:
            async with locks.hold("ABCDE"):
                first_acquired.set()
                await release_first.wait()

        async def second() -> None:
            async with locks.hold("ABCDE"):
                second_acquired.set()

        first_task = asyncio.create_task(first())
        await first_acquired.wait()
        second_task = asyncio.create_task(second())
        await asyncio.sleep(0)
        self.assertFalse(second_acquired.is_set())
        release_first.set()
        await asyncio.gather(first_task, second_task)
        self.assertTrue(second_acquired.is_set())


if __name__ == "__main__":
    unittest.main()
