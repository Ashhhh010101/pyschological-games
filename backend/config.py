"""Typed, immutable-by-convention configuration for the game engine."""

from typing import Literal, TypedDict

GameId = Literal["vault", "burden", "chain", "insurance", "reputation"]


class GameDefinition(TypedDict):
    """Static metadata and initial resources for one game mode."""

    name: str
    rounds: int
    stats: dict[str, int]


MAX_PLAYERS = 10
MIN_PLAYERS = 2  # Two players keeps local development practical.

GAME_CONFIG: dict[GameId, GameDefinition] = {
    "vault": {
        "name": "The Vault",
        "rounds": 5,
        "stats": {
            "liquid": 100,
            "vault": 0,
            "keys": 2,
            "seals": 1,
            "penalties": 0,
            "rescueBonus": 0,
        },
    },
    "burden": {
        "name": "The Burden",
        "rounds": 6,
        "stats": {"wealth": 100, "seals": 3, "debtScars": 0, "supportBonus": 0},
    },
    "chain": {
        "name": "Chain of Responsibility",
        "rounds": 8,
        "stats": {"secured": 20, "unsecured": 0, "refusals": 2, "courage": 0, "breaker": 0},
    },
    "insurance": {
        "name": "Insurance Market",
        "rounds": 5,
        "stats": {"assets": 100, "liquid": 40, "premiums": 0, "obligations": 0, "reliability": 0},
    },
    "reputation": {
        "name": "Reputation Economy",
        "rounds": 5,
        "stats": {
            "reputation": 60,
            "ambitions": 0,
            "keptPromises": 0,
            "brokenPromises": 0,
            "alignment": 0,
        },
    },
}
