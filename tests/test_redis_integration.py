import asyncio
import os
import unittest
from uuid import uuid4

from backend.domain.exceptions import RateLimitExceeded
from backend.infrastructure.redis.cache import RedisCache
from backend.infrastructure.redis.lock import RedisLockManager
from backend.infrastructure.redis.pubsub import RedisEventBus
from backend.infrastructure.redis.rate_limit import RedisRateLimiter

TEST_REDIS_URL = os.getenv("TEST_REDIS_URL")


@unittest.skipUnless(TEST_REDIS_URL, "TEST_REDIS_URL is required for Redis integration tests")
class RedisIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_cache_rate_limit_and_cross_instance_fanout(self) -> None:
        prefix = f"test-{uuid4()}"
        url = TEST_REDIS_URL or "redis://127.0.0.1:6379/15"
        cache = RedisCache(url, prefix)
        limiter = RedisRateLimiter(url, prefix)
        first = RedisEventBus(url, prefix)
        second = RedisEventBus(url, prefix)
        first_locks = RedisLockManager(url, prefix, timeout_seconds=5, wait_seconds=2)
        second_locks = RedisLockManager(url, prefix, timeout_seconds=5, wait_seconds=2)
        first_received = asyncio.Event()
        second_received = asyncio.Event()

        async def first_handler(code: str, version: int) -> None:
            if (code, version) == ("ABCDE", 12):
                first_received.set()

        async def second_handler(code: str, version: int) -> None:
            if (code, version) == ("ABCDE", 12):
                second_received.set()

        try:
            await first.start(first_handler)
            await second.start(second_handler)
            await cache.set("room:ABCDE", "12", 60)
            self.assertEqual(await cache.get("room:ABCDE"), "12")
            await limiter.check("action", "player", "2/minute")
            await limiter.check("action", "player", "2/minute")
            with self.assertRaises(RateLimitExceeded):
                await limiter.check("action", "player", "2/minute")
            await first.publish("ABCDE", 12)
            await asyncio.wait_for(first_received.wait(), timeout=2)
            await asyncio.wait_for(second_received.wait(), timeout=2)

            second_lock_acquired = asyncio.Event()

            async def acquire_second_lock() -> None:
                async with second_locks.hold("ABCDE"):
                    second_lock_acquired.set()

            async with first_locks.hold("ABCDE"):
                second_lock_task = asyncio.create_task(acquire_second_lock())
                await asyncio.sleep(0.05)
                self.assertFalse(second_lock_acquired.is_set())
            await asyncio.wait_for(second_lock_task, timeout=2)
            self.assertTrue(second_lock_acquired.is_set())
        finally:
            await first.close()
            await second.close()
            await limiter.close()
            await first_locks.close()
            await second_locks.close()
            await cache.close()


if __name__ == "__main__":
    unittest.main()
