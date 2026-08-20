"""Domain models and score calculation for game rooms."""

import time
from dataclasses import dataclass, field
from typing import Any, Literal, TypedDict

from backend.config import GameId

Phase = Literal["lobby", "decision", "results", "finished"]


class Prompt(TypedDict):
    title: str
    subtitle: str


@dataclass(slots=True)
class Action:
    values: dict[str, Any]
    idempotency_key: str


@dataclass(slots=True)
class Player:
    id: str
    name: str
    stats: dict[str, int]
    action: Action | None = None

    def score(self, game_id: GameId) -> int:
        """Calculate the documented final score for the selected game."""
        stats = self.stats
        if game_id == "vault":
            value = (
                stats["vault"] + stats["liquid"] * 0.5 + stats["keys"] * 3 - stats["penalties"] + stats["rescueBonus"]
            )
        elif game_id == "burden":
            value = stats["wealth"] * (1 - 0.12 * stats["debtScars"]) + stats["supportBonus"]
        elif game_id == "chain":
            value = stats["secured"] + stats["courage"] * 10 - stats["breaker"] * 5
        elif game_id == "insurance":
            value = stats["assets"] + stats["liquid"] + stats["premiums"] - stats["obligations"] + stats["reliability"]
        else:
            value = (
                stats["ambitions"] * 30
                + stats["reputation"] / 2
                + stats["keptPromises"] * 5
                - stats["brokenPromises"] * 8
                + stats["alignment"]
            )
        return round(value)


@dataclass(slots=True)
class Room:
    code: str
    game_id: GameId
    host_id: str
    players: dict[str, Player]
    phase: Phase = "lobby"
    round_number: int = 0
    prompt: Prompt | None = None
    hidden: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    data: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: float = field(default_factory=time.time)
