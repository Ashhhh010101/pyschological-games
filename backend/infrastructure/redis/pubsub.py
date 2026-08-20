"""Room-version fan-out for one-process and multi-instance deployments."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import Any

from redis.asyncio import Redis
from redis.asyncio.client import PubSub

from backend.domain.repositories import EventHandler


class LocalEventBus:
    def __init__(self) -> None:
        self._handler: EventHandler | None = None

    async def start(self, handler: EventHandler) -> None:
        self._handler = handler

    async def publish(self, room_code: str, version: int) -> None:
        if self._handler is not None:
            await self._handler(room_code, version)

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        self._handler = None


class RedisEventBus:
    def __init__(self, url: str, prefix: str) -> None:
        self.client: Redis = Redis.from_url(url, decode_responses=True)
        self.channel = f"{prefix}:room-events"
        self._pubsub: PubSub | None = None
        self._task: asyncio.Task[None] | None = None
        self._handler: EventHandler | None = None

    async def start(self, handler: EventHandler) -> None:
        self._handler = handler
        self._pubsub = self.client.pubsub(ignore_subscribe_messages=True)
        await self._pubsub.subscribe(self.channel)
        self._task = asyncio.create_task(self._listen(), name="redis-room-events")

    async def publish(self, room_code: str, version: int) -> None:
        await self.client.publish(self.channel, json.dumps({"code": room_code, "version": version}))

    async def ready(self) -> bool:
        try:
            return bool(await self.client.ping()) and self._task is not None and not self._task.done()
        except Exception:
            return False

    async def close(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._pubsub is not None:
            await self._pubsub.unsubscribe(self.channel)
            await self._pubsub.aclose()
        await self.client.aclose()

    async def _listen(self) -> None:
        if self._pubsub is None:
            return
        async for message in self._pubsub.listen():
            await self._handle_message(message)

    async def _handle_message(self, message: dict[str, Any]) -> None:
        if self._handler is None or message.get("type") != "message":
            return
        raw = message.get("data")
        try:
            value = json.loads(str(raw))
            code, version = str(value["code"]), int(value["version"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            return
        await self._handler(code, version)
