"""Durable player action and idempotency records."""

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.repositories import IdempotencyResult
from backend.infrastructure.database.models import IdempotencyRecord, PlayerActionRecord


class SQLAlchemyActionRepository:
    async def find_idempotency(
        self,
        session: AsyncSession,
        player_id: str,
        operation: str,
        key: str,
    ) -> IdempotencyResult | None:
        record = await session.scalar(
            select(IdempotencyRecord).where(
                IdempotencyRecord.player_id == player_id,
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.key == key,
            )
        )
        return IdempotencyResult(record.operation, record.response) if record else None

    async def add_action(
        self,
        session: AsyncSession,
        room_code: str,
        player_id: str,
        round_number: int,
        operation: str,
        key: str,
        values: dict[str, Any],
    ) -> None:
        session.add(
            PlayerActionRecord(
                room_code=room_code,
                player_id=player_id,
                round_number=round_number,
                operation=operation,
                idempotency_key=key,
                payload=values,
                created_at=datetime.now(timezone.utc),
            )
        )

    async def add_idempotency(
        self,
        session: AsyncSession,
        room_code: str,
        player_id: str,
        operation: str,
        key: str,
        response: dict[str, Any],
    ) -> None:
        session.add(
            IdempotencyRecord(
                room_code=room_code,
                player_id=player_id,
                operation=operation,
                key=key,
                response=response,
                created_at=datetime.now(timezone.utc),
            )
        )
