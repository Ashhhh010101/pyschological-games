"""Normalized SQL persistence schema with an authoritative room snapshot."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoomRecord(TimestampMixin, Base):
    __tablename__ = "rooms"
    code: Mapped[str] = mapped_column(String(5), primary_key=True)
    game_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    host_player_id: Mapped[str] = mapped_column(String(64), nullable=False)
    phase: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    expired_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    players: Mapped[list[PlayerRecord]] = relationship(cascade="all, delete-orphan", back_populates="room")
    __mapper_args__ = {"version_id_col": revision}


class PlayerRecord(Base):
    __tablename__ = "players"
    __table_args__ = (UniqueConstraint("room_code", "normalized_name", name="uq_player_room_name"),)
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    room_code: Mapped[str] = mapped_column(ForeignKey("rooms.code", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(24), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(24), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    room: Mapped[RoomRecord] = relationship(back_populates="players")


class GameSessionRecord(Base):
    __tablename__ = "game_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_code: Mapped[str] = mapped_column(ForeignKey("rooms.code", ondelete="CASCADE"), unique=True, index=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RoundRecord(Base):
    __tablename__ = "rounds"
    __table_args__ = (UniqueConstraint("room_code", "number", name="uq_round_room_number"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_code: Mapped[str] = mapped_column(ForeignKey("rooms.code", ondelete="CASCADE"), index=True)
    number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    prompt: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class PlayerActionRecord(Base):
    __tablename__ = "player_actions"
    __table_args__ = (
        UniqueConstraint("player_id", "operation", "idempotency_key", name="uq_action_idempotency"),
        Index("ix_action_room_round", "room_code", "round_number"),
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_code: Mapped[str] = mapped_column(ForeignKey("rooms.code", ondelete="CASCADE"))
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"))
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(128), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GameStateSnapshotRecord(Base):
    __tablename__ = "game_state_snapshots"
    __table_args__ = (UniqueConstraint("room_code", "version", name="uq_snapshot_room_version"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_code: Mapped[str] = mapped_column(ForeignKey("rooms.code", ondelete="CASCADE"), index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    state: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class ResultRecord(Base):
    __tablename__ = "results"
    __table_args__ = (UniqueConstraint("room_code", "round_number", name="uq_result_room_round"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_code: Mapped[str] = mapped_column(ForeignKey("rooms.code", ondelete="CASCADE"), index=True)
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class IdempotencyRecord(Base):
    __tablename__ = "idempotency_records"
    __table_args__ = (UniqueConstraint("player_id", "operation", "key", name="uq_idempotency_operation"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    room_code: Mapped[str] = mapped_column(ForeignKey("rooms.code", ondelete="CASCADE"), index=True)
    player_id: Mapped[str] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), index=True)
    operation: Mapped[str] = mapped_column(String(64), nullable=False)
    key: Mapped[str] = mapped_column(String(128), nullable=False)
    response: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class GameEventRecord(Base):
    __tablename__ = "game_events"
    __table_args__ = (UniqueConstraint("room_code", "sequence_number", name="uq_event_room_sequence"),)
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    room_code: Mapped[str] = mapped_column(ForeignKey("rooms.code", ondelete="CASCADE"), index=True)
    sequence_number: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
