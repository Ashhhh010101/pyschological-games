"""Async adapter retained for deterministic in-memory engine unit tests."""

from typing import Any

from backend.config import GameId
from backend.game import GameStore


class LegacyRoomService:
    def __init__(self, store: GameStore) -> None:
        self.store = store

    async def create_room(self, name: str, game_id: GameId) -> dict[str, str]:
        room, player = self.store.create_room(name, game_id)
        return {"code": room.code, "playerId": player.id}

    async def join_room(self, code: str, name: str) -> dict[str, str]:
        room, player = self.store.join_room(code, name)
        return {"code": room.code, "playerId": player.id}

    async def public_state(self, code: str, token: str) -> dict[str, Any]:
        return self.store.public_state(code, token)

    async def start(self, code: str, token: str, key: str | None = None) -> dict[str, Any]:
        self.store.start(code, token)
        return self.store.public_state(code, token)

    async def force_resolve(self, code: str, token: str, key: str | None = None) -> dict[str, Any]:
        self.store.force_resolve(code, token)
        return self.store.public_state(code, token)

    async def next_round(self, code: str, token: str, key: str | None = None) -> dict[str, Any]:
        self.store.next_round(code, token)
        return self.store.public_state(code, token)

    async def submit_action(
        self,
        code: str,
        token: str,
        values: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:
        self.store.submit_action(code, token, values, key)
        return self.store.public_state(code, token)

    async def expire_idle_rooms(self) -> list[str]:
        return []

    async def active_room_count(self) -> int:
        return self.store.room_count
