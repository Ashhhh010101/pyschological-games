"""Transactional application service around the existing game engine."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from random import SystemRandom
from typing import Any

from backend.application.session_service import SessionService
from backend.config import GameId
from backend.domain.events import EventType
from backend.domain.exceptions import ConcurrentMutation, InvalidGameAction, UnauthorizedPlayer
from backend.domain.repositories import Cache, EventPublisher, RoomRepository, RoomTransaction
from backend.game import GameError, GameStore
from backend.models import Room


class NullEventPublisher:
    async def publish(self, room_code: str, version: int) -> None:
        return None


class NullCache:
    async def get(self, key: str) -> str | None:
        return None

    async def set(self, key: str, value: str, ttl_seconds: int) -> None:
        return None

    async def delete(self, key: str) -> None:
        return None

    async def ready(self) -> bool:
        return True

    async def close(self) -> None:
        return None


class RoomService:
    """Authenticate commands and commit engine mutations as atomic SQL transactions."""

    def __init__(
        self,
        repository: RoomRepository,
        sessions: SessionService,
        publisher: EventPublisher | None = None,
        cache: Cache | None = None,
        room_ttl_seconds: int = 3600,
    ) -> None:
        self.repository = repository
        self.sessions = sessions
        self.publisher = publisher or NullEventPublisher()
        self.cache = cache or NullCache()
        self.room_ttl_seconds = room_ttl_seconds

    @staticmethod
    def _engine(room: Room | None = None) -> GameStore:
        engine = GameStore(SystemRandom())
        if room is not None:
            engine.rooms[room.code] = room
        return engine

    async def create_room(self, name: str, game_id: GameId) -> dict[str, str]:
        for _ in range(5):
            engine = self._engine()
            try:
                room, _ = engine.create_room(name, game_id)
            except GameError as exc:
                raise InvalidGameAction(str(exc)) from exc
            credential = self.sessions.issue()
            try:
                await self.repository.create(room, credential.token_hash, credential.expires_at)
            except ConcurrentMutation:
                continue
            await self._touch(room.code, room.version)
            await self.publisher.publish(room.code, room.version)
            return {"code": room.code, "playerId": credential.token}
        raise ConcurrentMutation("Could not allocate a unique room after several attempts.")

    async def join_room(self, code: str, name: str) -> dict[str, str]:
        credential = self.sessions.issue()
        async with self.repository.transaction(code) as transaction:
            engine = self._engine(transaction.room)
            try:
                _, player = engine.join_room(code, name)
            except GameError as exc:
                raise InvalidGameAction(str(exc)) from exc
            await transaction.add_player_credential(player.id, credential.token_hash, credential.expires_at)
            await transaction.add_event(EventType.PLAYER_JOINED, {"playerId": player.id})
            version = transaction.room.version
        await self.publisher.publish(code.upper(), version)
        await self._touch(code, version)
        return {"code": code.upper(), "playerId": credential.token}

    async def public_state(self, code: str, token: str) -> dict[str, Any]:
        room, player_id = await self.repository.load_authenticated(code, self.sessions.hash_token(token))
        return self._engine(room).public_state(room.code, player_id)

    async def start(self, code: str, token: str, key: str | None = None) -> dict[str, Any]:
        return await self._command(code, token, "start", key, EventType.GAME_STARTED, lambda e, c, p: e.start(c, p))

    async def force_resolve(self, code: str, token: str, key: str | None = None) -> dict[str, Any]:
        return await self._command(
            code,
            token,
            "resolve",
            key,
            EventType.ROUND_RESOLVED,
            lambda engine, room_code, player_id: engine.force_resolve(room_code, player_id),
        )

    async def next_round(self, code: str, token: str, key: str | None = None) -> dict[str, Any]:
        return await self._command(
            code,
            token,
            "next",
            key,
            EventType.ROUND_ADVANCED,
            lambda engine, room_code, player_id: engine.next_round(room_code, player_id),
        )

    async def submit_action(
        self,
        code: str,
        token: str,
        values: dict[str, Any],
        key: str,
    ) -> dict[str, Any]:
        token_hash = self.sessions.hash_token(token)
        async with self.repository.transaction(code, token_hash) as transaction:
            player_id = self._require_player(transaction)
            repeated = await transaction.find_idempotency("action", key)
            if repeated:
                return repeated.response
            engine = self._engine(transaction.room)
            previous_phase = transaction.room.phase
            try:
                engine.submit_action(code, player_id, values, key)
            except GameError as exc:
                raise InvalidGameAction(str(exc)) from exc
            response = engine.public_state(code, player_id)
            await transaction.record_action(player_id, "action", key, values)
            await transaction.record_idempotency(player_id, "action", key, response)
            await transaction.add_event(
                EventType.ACTION_SUBMITTED,
                {"playerId": player_id, "round": transaction.room.round_number},
            )
            if previous_phase != "results" and transaction.room.phase == "results":
                await transaction.add_event(
                    EventType.ROUND_RESOLVED,
                    {"round": transaction.room.round_number, "forced": False},
                )
            version = transaction.room.version
        await self.publisher.publish(code.upper(), version)
        await self._touch(code, version)
        return response

    async def expire_idle_rooms(self) -> list[str]:
        expired = await self.repository.expire_idle(datetime.now(timezone.utc))
        for code in expired:
            await self.cache.delete(f"room:{code}")
            await self.publisher.publish(code, -1)
        return expired

    async def active_room_count(self) -> int:
        return await self.repository.active_count()

    async def _command(
        self,
        code: str,
        token: str,
        operation: str,
        key: str | None,
        event_type: EventType,
        mutation: Callable[[GameStore, str, str], Room],
    ) -> dict[str, Any]:
        token_hash = self.sessions.hash_token(token)
        async with self.repository.transaction(code, token_hash) as transaction:
            player_id = self._require_player(transaction)
            if key:
                repeated = await transaction.find_idempotency(operation, key)
                if repeated:
                    return repeated.response
            engine = self._engine(transaction.room)
            try:
                mutation(engine, code, player_id)
            except GameError as exc:
                raise InvalidGameAction(str(exc)) from exc
            response = engine.public_state(code, player_id)
            payload = {"playerId": player_id, "round": transaction.room.round_number}
            await transaction.add_event(
                EventType.GAME_COMPLETED if transaction.room.phase == "finished" else event_type,
                payload,
            )
            if key:
                await transaction.record_idempotency(player_id, operation, key, response)
            version = transaction.room.version
        await self.publisher.publish(code.upper(), version)
        await self._touch(code, version)
        return response

    async def _touch(self, code: str, version: int) -> None:
        await self.cache.set(f"room:{code.upper()}", str(version), self.room_ttl_seconds)

    @staticmethod
    def _require_player(transaction: RoomTransaction) -> str:
        if transaction.player_id is None:
            raise UnauthorizedPlayer("A valid player session is required.")
        return transaction.player_id
