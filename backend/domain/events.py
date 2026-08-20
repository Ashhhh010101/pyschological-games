"""Public event names; payloads must never contain unrevealed decisions."""

from enum import Enum


class EventType(str, Enum):
    ROOM_CREATED = "ROOM_CREATED"
    PLAYER_JOINED = "PLAYER_JOINED"
    GAME_STARTED = "GAME_STARTED"
    ACTION_SUBMITTED = "ACTION_SUBMITTED"
    ROUND_RESOLVED = "ROUND_RESOLVED"
    ROUND_ADVANCED = "ROUND_ADVANCED"
    GAME_COMPLETED = "GAME_COMPLETED"
    ROOM_EXPIRED = "ROOM_EXPIRED"
