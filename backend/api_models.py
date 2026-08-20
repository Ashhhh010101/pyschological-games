"""Pydantic request contracts for the HTTP API."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.config import GameId


class APIModel(BaseModel):
    """Reject unknown input while keeping the public API in camel case."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class CreateRoomRequest(APIModel):
    name: str = Field(min_length=1, max_length=24)
    game_id: GameId = Field(alias="gameId")


class JoinRoomRequest(APIModel):
    name: str = Field(min_length=1, max_length=24)


class PlayerRequest(APIModel):
    player_id: str = Field(alias="playerId", min_length=1, max_length=128)
    idempotency_key: str | None = Field(default=None, alias="idempotencyKey", min_length=1, max_length=128)


class ActionRequest(PlayerRequest):
    idempotency_key: str = Field(alias="idempotencyKey", min_length=1, max_length=128)
    values: dict[str, Any]
