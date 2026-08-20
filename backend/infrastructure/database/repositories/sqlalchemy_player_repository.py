"""Player credential persistence."""

from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.domain.exceptions import UnauthorizedPlayer
from backend.infrastructure.database.models import PlayerRecord
from backend.models import Player


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


class SQLAlchemyPlayerRepository:
    async def add(
        self,
        session: AsyncSession,
        room_code: str,
        player: Player,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        session.add(
            PlayerRecord(
                id=player.id,
                room_code=room_code,
                name=player.name,
                normalized_name=player.name.casefold(),
                token_hash=token_hash,
                token_expires_at=expires_at,
                revoked_at=None,
                created_at=utc_now(),
            )
        )

    async def authenticate(
        self,
        session: AsyncSession,
        room_code: str,
        token_hash: str,
    ) -> str:
        record = await session.scalar(
            select(PlayerRecord).where(
                PlayerRecord.room_code == room_code,
                PlayerRecord.token_hash == token_hash,
            )
        )
        if record is None or record.revoked_at is not None or as_utc(record.token_expires_at) <= utc_now():
            raise UnauthorizedPlayer("The player session is invalid or expired.")
        return record.id
