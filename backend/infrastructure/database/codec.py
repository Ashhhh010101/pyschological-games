"""JSON snapshot conversion isolated from the game engine."""

from typing import Any, cast

from backend.config import GameId
from backend.models import Action, Phase, Player, Prompt, Room


def encode_room(room: Room) -> dict[str, Any]:
    return {
        "code": room.code,
        "gameId": room.game_id,
        "hostId": room.host_id,
        "players": [
            {
                "id": player.id,
                "name": player.name,
                "stats": player.stats,
                "action": (
                    {"values": player.action.values, "idempotencyKey": player.action.idempotency_key}
                    if player.action
                    else None
                ),
            }
            for player in room.players.values()
        ],
        "phase": room.phase,
        "roundNumber": room.round_number,
        "prompt": room.prompt,
        "hidden": room.hidden,
        "result": room.result,
        "data": room.data,
        "version": room.version,
        "createdAt": room.created_at,
    }


def decode_room(value: dict[str, Any]) -> Room:
    players: dict[str, Player] = {}
    for item in value["players"]:
        action_value = item.get("action")
        action = Action(dict(action_value["values"]), str(action_value["idempotencyKey"])) if action_value else None
        player = Player(str(item["id"]), str(item["name"]), dict(item["stats"]), action)
        players[player.id] = player
    return Room(
        code=str(value["code"]),
        game_id=cast(GameId, value["gameId"]),
        host_id=str(value["hostId"]),
        players=players,
        phase=cast(Phase, value["phase"]),
        round_number=int(value["roundNumber"]),
        prompt=cast(Prompt | None, value.get("prompt")),
        hidden=dict(value.get("hidden", {})),
        result=value.get("result"),
        data=dict(value.get("data", {})),
        version=int(value["version"]),
        created_at=float(value["createdAt"]),
    )
