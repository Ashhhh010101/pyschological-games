import asyncio
import unittest
from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi import FastAPI
from redis.exceptions import LockError
from sqlalchemy.exc import SQLAlchemyError

from backend.application.legacy_room_service import LegacyRoomService
from backend.application.room_service import NullCache, NullEventPublisher, NullLockManager
from backend.connections import ConnectionManager
from backend.domain.exceptions import ApplicationError, ConcurrentMutation, RateLimitExceeded
from backend.game import GameStore
from backend.infrastructure.http import PayloadSizeLimitMiddleware
from backend.infrastructure.observability.telemetry import Observability, configure_telemetry
from backend.infrastructure.redis.cache import MemoryCache, RedisCache
from backend.infrastructure.redis.lock import MemoryLockManager, RedisLockManager
from backend.infrastructure.redis.pubsub import LocalEventBus, RedisEventBus
from backend.infrastructure.redis.rate_limit import MemoryRateLimiter, RedisRateLimiter, parse_limit
from backend.migrate import wait_for_database
from backend.settings import Settings


class InfrastructureTests(unittest.IsolatedAsyncioTestCase):
    async def test_memory_adapters_cover_lifecycle_and_expiry(self) -> None:
        cache = MemoryCache()
        await cache.set("expired", "value", 0)
        self.assertIsNone(await cache.get("expired"))
        self.assertTrue(await cache.ready())
        await cache.set("live", "value", 10)
        await cache.close()
        self.assertIsNone(await cache.get("live"))

        locks = MemoryLockManager()
        await locks.close()
        limiter = MemoryRateLimiter(enabled=False)
        await limiter.check("scope", "identity", "invalid")
        limiter.enabled = True
        with patch("backend.infrastructure.redis.rate_limit.time.monotonic", side_effect=[0.0, 2.0]):
            await limiter.check("scope", "identity", "1/second")
            await limiter.check("scope", "identity", "1/second")
        await limiter.close()
        with self.assertRaises(ValueError):
            parse_limit("never")

        bus = LocalEventBus()
        await bus.publish("ABCDE", 1)
        self.assertTrue(await bus.ready())

    async def test_redis_cache_success_failure_and_close(self) -> None:
        client = AsyncMock()
        with patch("backend.infrastructure.redis.cache.Redis.from_url", return_value=client):
            cache = RedisCache("redis://test", "prefix")
        client.get.side_effect = [7, None]
        self.assertEqual(await cache.get("key"), "7")
        self.assertIsNone(await cache.get("missing"))
        await cache.set("key", "value", 12)
        await cache.delete("key")
        client.ping.return_value = True
        self.assertTrue(await cache.ready())
        client.ping.side_effect = RuntimeError
        self.assertFalse(await cache.ready())
        await cache.close()
        client.set.assert_awaited_once_with("prefix:key", "value", ex=12)

    async def test_redis_rate_limiter_and_lock_paths(self) -> None:
        client = MagicMock()
        client.eval = AsyncMock(side_effect=[1, 2])
        client.aclose = AsyncMock()
        with patch("backend.infrastructure.redis.rate_limit.Redis.from_url", return_value=client):
            limiter = RedisRateLimiter("redis://test", "prefix")
        await limiter.check("scope", "id", "1/second")
        with self.assertRaises(RateLimitExceeded):
            await limiter.check("scope", "id", "1/second")
        limiter.enabled = False
        await limiter.check("scope", "id", "invalid")
        await limiter.close()

        lock = MagicMock()
        lock.acquire = AsyncMock(return_value=False)
        lock.release = AsyncMock()
        client.lock.return_value = lock
        with patch("backend.infrastructure.redis.lock.Redis.from_url", return_value=client):
            manager = RedisLockManager("redis://test", "prefix", 10, 2)
        with self.assertRaises(ConcurrentMutation):
            async with manager.hold("ABCDE"):
                pass
        lock.acquire.return_value = True
        lock.release.side_effect = LockError
        async with manager.hold("ABCDE"):
            pass
        await manager.close()

    async def test_redis_event_bus_all_message_and_lifecycle_paths(self) -> None:
        client = MagicMock()
        client.publish = AsyncMock()
        client.ping = AsyncMock(return_value=True)
        client.aclose = AsyncMock()
        pubsub = MagicMock()
        pubsub.subscribe = AsyncMock()
        pubsub.unsubscribe = AsyncMock()
        pubsub.aclose = AsyncMock()
        client.pubsub.return_value = pubsub
        with patch("backend.infrastructure.redis.pubsub.Redis.from_url", return_value=client):
            bus = RedisEventBus("redis://test", "prefix")
        received: list[tuple[str, int]] = []

        async def handler(code: str, version: int) -> None:
            received.append((code, version))

        await bus._handle_message({"type": "message", "data": "{}"})
        bus._handler = handler
        await bus._handle_message({"type": "subscribe", "data": "ignored"})
        await bus._handle_message({"type": "message", "data": "bad-json"})
        await bus._handle_message({"type": "message", "data": '{"code":"ABCDE","version":3}'})
        self.assertEqual(received, [("ABCDE", 3)])
        await bus.publish("ABCDE", 4)
        self.assertFalse(await bus.ready())
        bus._task = asyncio.create_task(asyncio.sleep(10))
        self.assertTrue(await bus.ready())
        client.ping.side_effect = RuntimeError
        self.assertFalse(await bus.ready())
        bus._pubsub = pubsub
        await bus.close()

        empty_bus = RedisEventBus("redis://test", "prefix")
        await empty_bus._listen()

    async def test_connection_manager_sync_async_failures_and_closure(self) -> None:
        manager = ConnectionManager()
        first, second, third = AsyncMock(), AsyncMock(), AsyncMock()
        await manager.connect(first, "ABCDE", "one")
        await manager.connect(second, "ABCDE", "two")
        await manager.connect(third, "OTHER", "three")
        manager.disconnect(AsyncMock(), "MISSING", "none")

        async def async_state(player_id: str) -> dict[str, str]:
            return {"id": player_id}

        await manager.broadcast("ABCDE", async_state)

        def failing_state(_player_id: str) -> dict[str, str]:
            raise ApplicationError("bad")

        await manager.broadcast("ABCDE", failing_state)
        self.assertNotIn("ABCDE", manager._rooms)
        await manager.close_all()
        self.assertEqual(manager._rooms, {})

    async def test_payload_middleware_transport_paths(self) -> None:
        app = AsyncMock()
        middleware = PayloadSizeLimitMiddleware(app, 3)
        send = AsyncMock()

        await middleware({"type": "websocket"}, AsyncMock(), send)
        self.assertEqual(app.await_count, 1)

        receive = AsyncMock(return_value={"type": "http.disconnect"})
        await middleware({"type": "http", "headers": []}, receive, send)
        replay = app.await_args.args[1]
        self.assertEqual((await replay())["type"], "http.disconnect")
        self.assertEqual((await replay())["body"], b"")

        await middleware({"type": "http", "headers": [(b"content-length", b"bad")]}, AsyncMock(), send)
        receive = AsyncMock(return_value={"type": "http.request", "body": b"four"})
        await middleware({"type": "http", "headers": []}, receive, send)

    async def test_database_wait_retries_and_disposes(self) -> None:
        connection = AsyncMock()
        connection.execute.side_effect = [SQLAlchemyError("wait"), None]

        @asynccontextmanager
        async def connect():
            yield connection

        engine = MagicMock()
        engine.connect = connect
        engine.dispose = AsyncMock()
        settings = Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            database_connect_attempts=2,
            database_retry_delay_seconds=0.1,
        )
        with (
            patch("backend.migrate.create_database", return_value=(engine, MagicMock())),
            patch("backend.migrate.asyncio.sleep", new=AsyncMock()),
        ):
            await wait_for_database(settings)
        engine.dispose.assert_awaited_once()

        connection.execute.side_effect = SQLAlchemyError("down")
        with (
            patch("backend.migrate.create_database", return_value=(engine, MagicMock())),
            self.assertRaises(SQLAlchemyError),
        ):
            await wait_for_database(settings.model_copy(update={"database_connect_attempts": 1}))

    async def test_null_and_legacy_adapters(self) -> None:
        publisher, cache, locks = NullEventPublisher(), NullCache(), NullLockManager()
        await publisher.publish("ABCDE", 1)
        self.assertIsNone(await cache.get("key"))
        await cache.set("key", "value", 1)
        await cache.delete("key")
        self.assertTrue(await cache.ready())
        await cache.close()
        async with locks.hold("ABCDE"):
            pass
        await locks.close()

        service = LegacyRoomService(GameStore())
        created = await service.create_room("Host", "vault")
        joined = await service.join_room(created["code"], "Guest")
        await service.start(created["code"], created["playerId"])
        await service.submit_action(
            created["code"],
            created["playerId"],
            {"deposit": 0, "useKey": False, "useSeal": False},
            "host-action",
        )
        await service.force_resolve(created["code"], created["playerId"])
        await service.next_round(created["code"], created["playerId"])
        guest_state = await service.public_state(created["code"], joined["playerId"])
        self.assertEqual(guest_state["viewerId"], joined["playerId"])
        self.assertEqual(await service.expire_idle_rooms(), [])
        self.assertEqual(await service.active_room_count(), 1)


class TelemetryTests(unittest.TestCase):
    def test_observability_records_and_shuts_down(self) -> None:
        request_counter, error_counter, latency = MagicMock(), MagicMock(), MagicMock()
        tracer, meter = MagicMock(), MagicMock()
        observability = Observability(request_counter, error_counter, latency, tracer, meter)
        observability.record_request("GET", "/route", 503, 1.5)
        request_counter.add.assert_called_once()
        error_counter.add.assert_called_once()
        latency.record.assert_called_once()
        observability.shutdown()
        tracer.shutdown.assert_called_once()
        meter.shutdown.assert_called_once()
        Observability().record_request("GET", "/", 200, 0)
        Observability().shutdown()

    @patch("backend.infrastructure.observability.telemetry.RedisInstrumentor")
    @patch("backend.infrastructure.observability.telemetry.SQLAlchemyInstrumentor")
    @patch("backend.infrastructure.observability.telemetry.FastAPIInstrumentor")
    @patch("backend.infrastructure.observability.telemetry.metrics.set_meter_provider")
    @patch("backend.infrastructure.observability.telemetry.trace.set_tracer_provider")
    @patch("backend.infrastructure.observability.telemetry.MeterProvider")
    @patch("backend.infrastructure.observability.telemetry.TracerProvider")
    def test_configure_telemetry_enabled_without_exporter(
        self,
        tracer_provider_class: MagicMock,
        meter_provider_class: MagicMock,
        _set_tracer: MagicMock,
        _set_meter: MagicMock,
        fastapi_instrumentor: MagicMock,
        sqlalchemy_instrumentor: MagicMock,
        redis_instrumentor: MagicMock,
    ) -> None:
        meter_provider = meter_provider_class.return_value
        meter = meter_provider.get_meter.return_value
        meter.create_counter.side_effect = [MagicMock(), MagicMock()]
        meter.create_histogram.return_value = MagicMock()
        engine = SimpleNamespace(sync_engine=MagicMock())
        settings = Settings(_env_file=None, app_env="test", otel_enabled=True)
        result = configure_telemetry(FastAPI(), settings, engine)  # type: ignore[arg-type]
        self.assertIs(result.tracer_provider, tracer_provider_class.return_value)
        fastapi_instrumentor.instrument_app.assert_called_once()
        sqlalchemy_instrumentor.return_value.instrument.assert_called_once()
        redis_instrumentor.return_value.instrument.assert_called_once()

    def test_configure_telemetry_disabled(self) -> None:
        result = configure_telemetry(FastAPI(), Settings(_env_file=None, app_env="test"), None)
        self.assertIsNone(result.request_counter)


if __name__ == "__main__":
    unittest.main()
