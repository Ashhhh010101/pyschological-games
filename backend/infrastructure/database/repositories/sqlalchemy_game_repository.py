"""Game session, round, result, snapshot, and event persistence."""

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.events import EventType
from backend.infrastructure.database.models import (
    GameEventRecord,
    GameSessionRecord,
    GameStateSnapshotRecord,
    ResultRecord,
    RoundRecord,
)
from backend.models import Room


class SQLAlchemyGameRepository:
    async def add_event(
        self,
        session: AsyncSession,
        room_code: str,
        event_type: EventType,
        payload: dict[str, Any],
    ) -> None:
        sequence = await session.scalar(
            select(func.coalesce(func.max(GameEventRecord.sequence_number), 0)).where(
                GameEventRecord.room_code == room_code
            )
        )
        session.add(
            GameEventRecord(
                id=str(uuid4()),
                room_code=room_code,
                sequence_number=int(sequence or 0) + 1,
                event_type=event_type.value,
                payload=payload,
                created_at=datetime.now(timezone.utc),
            )
        )

    def add_session(self, session: AsyncSession, room: Room) -> None:
        session.add(
            GameSessionRecord(
                id=str(uuid4()),
                room_code=room.code,
                status=room.phase,
                started_at=None,
                completed_at=None,
                created_at=datetime.now(timezone.utc),
            )
        )

    def add_snapshot(self, session: AsyncSession, room: Room, state: dict[str, Any]) -> None:
        session.add(
            GameStateSnapshotRecord(
                room_code=room.code,
                version=room.version,
                state=state,
                created_at=datetime.now(timezone.utc),
            )
        )

    async def sync_round_and_result(self, session: AsyncSession, room: Room) -> None:
        game_session = await session.scalar(select(GameSessionRecord).where(GameSessionRecord.room_code == room.code))
        now = datetime.now(timezone.utc)
        if game_session:
            game_session.status = room.phase
            if room.round_number and game_session.started_at is None:
                game_session.started_at = now
            if room.phase == "finished":
                game_session.completed_at = now
        if not room.round_number:
            return
        round_record = await session.scalar(
            select(RoundRecord).where(
                RoundRecord.room_code == room.code,
                RoundRecord.number == room.round_number,
            )
        )
        if round_record is None:
            round_record = RoundRecord(
                room_code=room.code,
                number=room.round_number,
                status=room.phase,
                prompt=room.prompt,
                created_at=now,
                resolved_at=None,
            )
            session.add(round_record)
        else:
            round_record.status = room.phase
        if room.phase in {"results", "finished"}:
            round_record.resolved_at = round_record.resolved_at or now
        if room.result is not None:
            existing = await session.scalar(
                select(ResultRecord).where(
                    ResultRecord.room_code == room.code,
                    ResultRecord.round_number == room.round_number,
                )
            )
            if existing is None:
                session.add(
                    ResultRecord(
                        room_code=room.code,
                        round_number=room.round_number,
                        payload=room.result,
                        created_at=now,
                    )
                )
