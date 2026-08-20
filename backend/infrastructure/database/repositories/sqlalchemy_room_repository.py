"""Authoritative transactional room repository."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker
from sqlalchemy.orm.exc import StaleDataError

from backend.domain.events import EventType
from backend.domain.exceptions import ConcurrentMutation, PersistenceError, RoomExpired, RoomNotFound
from backend.domain.repositories import IdempotencyResult
from backend.infrastructure.database.codec import decode_room, encode_room
from backend.infrastructure.database.models import Base, GameEventRecord, RoomRecord
from backend.infrastructure.database.repositories.sqlalchemy_action_repository import SQLAlchemyActionRepository
from backend.infrastructure.database.repositories.sqlalchemy_game_repository import SQLAlchemyGameRepository
from backend.infrastructure.database.repositories.sqlalchemy_player_repository import SQLAlchemyPlayerRepository, as_utc
from backend.models import Room


class SQLRoomTransaction:
    def __init__(
        self,
        session: AsyncSession,
        record: RoomRecord,
        room: Room,
        player_id: str | None,
        players: SQLAlchemyPlayerRepository,
        actions: SQLAlchemyActionRepository,
        games: SQLAlchemyGameRepository,
    ) -> None:
        self.session = session
        self.record = record
        self.room = room
        self.player_id = player_id
        self._players = players
        self._actions = actions
        self._games = games

    async def add_player_credential(self, player_id: str, token_hash: str, expires_at: datetime) -> None:
        await self._players.add(self.session, self.room.code, self.room.players[player_id], token_hash, expires_at)

    async def find_idempotency(self, operation: str, key: str) -> IdempotencyResult | None:
        if self.player_id is None:
            return None
        return await self._actions.find_idempotency(self.session, self.player_id, operation, key)

    async def record_action(
        self,
        player_id: str,
        operation: str,
        key: str,
        values: dict[str, Any],
    ) -> None:
        await self._actions.add_action(
            self.session,
            self.room.code,
            player_id,
            self.room.round_number,
            operation,
            key,
            values,
        )

    async def record_idempotency(
        self,
        player_id: str,
        operation: str,
        key: str,
        response: dict[str, Any],
    ) -> None:
        await self._actions.add_idempotency(
            self.session,
            self.room.code,
            player_id,
            operation,
            key,
            response,
        )

    async def add_event(self, event_type: EventType, payload: dict[str, Any]) -> None:
        await self._games.add_event(self.session, self.room.code, event_type, payload)


class SQLAlchemyRoomRepository:
    def __init__(
        self,
        engine: AsyncEngine,
        sessions: async_sessionmaker[AsyncSession],
        room_ttl_seconds: int,
        auto_create: bool = True,
    ) -> None:
        self.engine = engine
        self.sessions = sessions
        self.room_ttl = timedelta(seconds=room_ttl_seconds)
        self.auto_create = auto_create
        self.players = SQLAlchemyPlayerRepository()
        self.actions = SQLAlchemyActionRepository()
        self.games = SQLAlchemyGameRepository()

    async def initialize(self) -> None:
        if self.auto_create:
            async with self.engine.begin() as connection:
                await connection.run_sync(Base.metadata.create_all)

    async def close(self) -> None:
        await self.engine.dispose()

    async def ready(self) -> bool:
        try:
            async with self.engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
            return True
        except SQLAlchemyError:
            return False

    async def create(self, room: Room, token_hash: str, expires_at: datetime) -> None:
        now = datetime.now(timezone.utc)
        state = encode_room(room)
        try:
            async with self.sessions.begin() as session:
                session.add(
                    RoomRecord(
                        code=room.code,
                        game_id=room.game_id,
                        host_player_id=room.host_id,
                        phase=room.phase,
                        version=room.version,
                        revision=1,
                        expires_at=now + self.room_ttl,
                        expired_at=None,
                        snapshot=state,
                        created_at=now,
                        updated_at=now,
                    )
                )
                await self.players.add(session, room.code, room.players[room.host_id], token_hash, expires_at)
                self.games.add_session(session, room)
                self.games.add_snapshot(session, room, state)
                await self.games.add_event(session, room.code, EventType.ROOM_CREATED, {"gameId": room.game_id})
        except IntegrityError:
            raise ConcurrentMutation("The room code or credential already exists.") from None
        except SQLAlchemyError as exc:
            raise PersistenceError("Could not persist the room.") from exc

    async def load_authenticated(self, code: str, token_hash: str) -> tuple[Room, str]:
        normalized = code.upper()
        async with self.sessions() as session:
            record = await session.get(RoomRecord, normalized)
            if record is None:
                raise RoomNotFound("Room not found.")
            self._ensure_active(record)
            player_id = await self.players.authenticate(session, normalized, token_hash)
            return decode_room(record.snapshot), player_id

    @asynccontextmanager
    async def transaction(
        self,
        code: str,
        token_hash: str | None = None,
    ) -> AsyncIterator[SQLRoomTransaction]:
        normalized = code.upper()
        try:
            async with self.sessions() as session, session.begin():
                record = await session.scalar(select(RoomRecord).where(RoomRecord.code == normalized).with_for_update())
                if record is None:
                    raise RoomNotFound("Room not found.")
                self._ensure_active(record)
                player_id = await self.players.authenticate(session, normalized, token_hash) if token_hash else None
                room = decode_room(record.snapshot)
                initial_version = room.version
                transaction = SQLRoomTransaction(
                    session,
                    record,
                    room,
                    player_id,
                    self.players,
                    self.actions,
                    self.games,
                )
                yield transaction
                now = datetime.now(timezone.utc)
                state = encode_room(room)
                record.game_id = room.game_id
                record.host_player_id = room.host_id
                record.phase = room.phase
                record.version = room.version
                record.snapshot = state
                record.updated_at = now
                record.expires_at = now + self.room_ttl
                if room.version != initial_version:
                    self.games.add_snapshot(session, room, state)
                await self.games.sync_round_and_result(session, room)
        except (RoomNotFound, RoomExpired):
            raise
        except StaleDataError:
            raise ConcurrentMutation("The room changed concurrently; retry the operation.") from None
        except IntegrityError:
            raise ConcurrentMutation("The operation conflicts with a concurrent request.") from None
        except SQLAlchemyError as exc:
            raise PersistenceError("The room operation could not be committed.") from exc

    async def expire_idle(self, now: datetime) -> list[str]:
        expired: list[str] = []
        async with self.sessions() as session, session.begin():
            records = list(
                await session.scalars(
                    select(RoomRecord)
                    .where(RoomRecord.expires_at <= now, RoomRecord.expired_at.is_(None))
                    .with_for_update(skip_locked=True)
                )
            )
            for record in records:
                record.expired_at = now
                expired.append(record.code)
                sequence = await session.scalar(
                    select(GameEventRecord.sequence_number)
                    .where(GameEventRecord.room_code == record.code)
                    .order_by(GameEventRecord.sequence_number.desc())
                    .limit(1)
                )
                await self.games.add_event(
                    session,
                    record.code,
                    EventType.ROOM_EXPIRED,
                    {"lastSequence": int(sequence or 0)},
                )
        return expired

    async def active_count(self) -> int:
        async with self.sessions() as session:
            count = await session.scalar(
                select(func.count()).select_from(RoomRecord).where(RoomRecord.expired_at.is_(None))
            )
            return int(count or 0)

    @staticmethod
    def _ensure_active(record: RoomRecord) -> None:
        now = datetime.now(timezone.utc)
        if record.expired_at is not None or as_utc(record.expires_at) <= now:
            raise RoomExpired("This room has expired.")
