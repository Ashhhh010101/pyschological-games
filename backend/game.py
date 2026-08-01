from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from random import Random
from threading import RLock
from typing import Any
import secrets
import string
import time


MAX_PLAYERS = 10
MIN_PLAYERS = 2  # The source target is 3; two makes local testing practical.

GAME_CONFIG: dict[str, dict[str, Any]] = {
    "vault": {
        "name": "The Vault",
        "rounds": 5,
        "stats": {"liquid": 100, "vault": 0, "keys": 2, "seals": 1, "penalties": 0, "rescueBonus": 0},
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
        "stats": {"reputation": 60, "ambitions": 0, "keptPromises": 0, "brokenPromises": 0, "alignment": 0},
    },
}


class GameError(Exception):
    """A validation error that is safe to return to a client."""


@dataclass
class Action:
    values: dict[str, Any]
    idempotency_key: str


@dataclass
class Player:
    id: str
    name: str
    stats: dict[str, int]
    action: Action | None = None

    def score(self, game_id: str) -> int:
        s = self.stats
        if game_id == "vault":
            return round(s["vault"] + s["liquid"] * 0.5 + s["keys"] * 3 - s["penalties"] + s["rescueBonus"])
        if game_id == "burden":
            return round(s["wealth"] * (1 - 0.12 * s["debtScars"]) + s["supportBonus"])
        if game_id == "chain":
            return round(s["secured"] + s["courage"] * 10 - s["breaker"] * 5)
        if game_id == "insurance":
            return round(s["assets"] + s["liquid"] + s["premiums"] - s["obligations"] + s["reliability"])
        return round(
            s["ambitions"] * 30
            + s["reputation"] / 2
            + s["keptPromises"] * 5
            - s["brokenPromises"] * 8
            + s["alignment"]
        )


@dataclass
class Room:
    code: str
    game_id: str
    host_id: str
    players: dict[str, Player]
    phase: str = "lobby"
    round_number: int = 0
    prompt: dict[str, str] | None = None
    hidden: dict[str, Any] = field(default_factory=dict)
    result: dict[str, Any] | None = None
    data: dict[str, Any] = field(default_factory=dict)
    version: int = 1
    created_at: float = field(default_factory=time.time)


class GameStore:
    """Thread-safe room store with server-authoritative rules for all game modes."""

    def __init__(self, rng: Random | None = None) -> None:
        self.rooms: dict[str, Room] = {}
        self.rng = rng or Random()
        self.lock = RLock()

    def _player_id(self) -> str:
        return secrets.token_urlsafe(18)

    def _room_code(self) -> str:
        for _ in range(100):
            code = "".join(self.rng.choice(string.ascii_uppercase) for _ in range(5))
            if code not in self.rooms:
                return code
        raise GameError("Could not allocate a room code. Try again.")

    @staticmethod
    def _clean_name(name: Any) -> str:
        clean = " ".join(str(name or "").strip().split())
        if not 1 <= len(clean) <= 24:
            raise GameError("Name must contain 1 to 24 characters.")
        return clean

    @staticmethod
    def _new_stats(game_id: str) -> dict[str, int]:
        return deepcopy(GAME_CONFIG[game_id]["stats"])

    def _room(self, code: str) -> Room:
        room = self.rooms.get(code.upper())
        if room is None:
            raise GameError("Room not found.")
        return room

    @staticmethod
    def _player(room: Room, player_id: str) -> Player:
        player = room.players.get(player_id)
        if player is None:
            raise GameError("Player not found in this room.")
        return player

    def create_room(self, name: Any, game_id: Any = "vault") -> tuple[Room, Player]:
        with self.lock:
            selected = str(game_id or "vault").lower()
            if selected not in GAME_CONFIG:
                raise GameError("Unknown game selection.")
            player = Player(self._player_id(), self._clean_name(name), self._new_stats(selected))
            room = Room(self._room_code(), selected, player.id, {player.id: player})
            self.rooms[room.code] = room
            return room, player

    def join_room(self, code: str, name: Any) -> tuple[Room, Player]:
        with self.lock:
            room = self._room(code)
            if room.phase != "lobby":
                raise GameError("This game has already started.")
            if len(room.players) >= MAX_PLAYERS:
                raise GameError("This room is full.")
            clean_name = self._clean_name(name)
            if any(p.name.casefold() == clean_name.casefold() for p in room.players.values()):
                raise GameError("That name is already in use in this room.")
            player = Player(self._player_id(), clean_name, self._new_stats(room.game_id))
            room.players[player.id] = player
            room.version += 1
            return room, player

    def start(self, code: str, player_id: str) -> Room:
        with self.lock:
            room = self._room(code)
            self._require_host(room, player_id)
            if room.phase != "lobby":
                raise GameError("The game has already started.")
            if len(room.players) < MIN_PLAYERS:
                raise GameError(f"At least {MIN_PLAYERS} players are required.")
            self._start_round(room)
            return room

    def next_round(self, code: str, player_id: str) -> Room:
        with self.lock:
            room = self._room(code)
            self._require_host(room, player_id)
            if room.phase != "results":
                raise GameError("The current round is not ready to advance.")
            config = GAME_CONFIG[room.game_id]
            chain_ended = room.game_id == "chain" and room.data.get("ruptures", 0) >= 5
            if room.round_number >= config["rounds"] or chain_ended:
                room.phase = "finished"
                room.version += 1
            else:
                self._start_round(room)
            return room

    def submit_action(self, code: str, player_id: str, values: Any, idempotency_key: Any) -> Room:
        with self.lock:
            room = self._room(code)
            player = self._player(room, player_id)
            if room.phase != "decision":
                raise GameError("Actions are closed for this round.")
            key = str(idempotency_key or "").strip()
            if not key:
                raise GameError("An idempotency key is required.")
            if player.action:
                if player.action.idempotency_key == key:
                    return room
                raise GameError("You already submitted an action this round.")
            if not isinstance(values, dict):
                raise GameError("Action values must be an object.")
            clean_values = self._validate_action(room, player, values)
            player.action = Action(clean_values, key)
            room.version += 1
            if all(p.action is not None for p in room.players.values()):
                self._resolve(room, forced=False)
            return room

    def force_resolve(self, code: str, player_id: str) -> Room:
        with self.lock:
            room = self._room(code)
            self._require_host(room, player_id)
            if room.phase != "decision":
                raise GameError("This round cannot be resolved now.")
            for player in room.players.values():
                if player.action is None:
                    player.action = Action(self._safe_action(room, player), "afk-safe-action")
            self._resolve(room, forced=True)
            return room

    @staticmethod
    def _require_host(room: Room, player_id: str) -> None:
        if room.host_id != player_id:
            raise GameError("Only the room host can do that.")

    @staticmethod
    def _integer(value: Any, label: str, low: int, high: int) -> int:
        if isinstance(value, bool):
            raise GameError(f"{label} must be a whole number.")
        try:
            number = int(value)
        except (TypeError, ValueError):
            raise GameError(f"{label} must be a whole number.") from None
        if not low <= number <= high:
            raise GameError(f"{label} must be between {low} and {high}.")
        return number

    def _target(self, room: Room, player: Player, value: Any, required: bool) -> str:
        target = str(value or "")
        if not required and not target:
            return ""
        if target == player.id or target not in room.players:
            raise GameError("Choose another player as the target.")
        return target

    def _validate_action(self, room: Room, player: Player, values: dict[str, Any]) -> dict[str, Any]:
        game = room.game_id
        s = player.stats
        if game == "vault":
            return {
                "deposit": self._integer(values.get("deposit"), "Deposit", 0, s["liquid"]),
                "useKey": bool(values.get("useKey")) and s["keys"] > 0,
                "useSeal": bool(values.get("useSeal")) and s["seals"] > 0,
            }
        if game == "burden":
            protected = self._integer(values.get("protected"), "Protected wealth", 0, s["wealth"])
            exposed = self._integer(values.get("exposed"), "Exposed wealth", 0, s["wealth"])
            transferred = self._integer(values.get("transferred"), "Transferred wealth", 0, s["wealth"])
            if protected + exposed + transferred != s["wealth"]:
                raise GameError("Protected, exposed, and transferred amounts must equal your wealth.")
            target = self._target(room, player, values.get("target"), transferred > 0)
            return {"protected": protected, "exposed": exposed, "transferred": transferred, "target": target,
                    "useSeal": bool(values.get("useSeal")) and s["seals"] > 0}
        if game == "chain":
            stance = str(values.get("stance", ""))
            if stance not in {"carry", "pass", "refuse", "redirect", "bank"}:
                raise GameError("Choose how to handle the Charge.")
            if stance == "refuse" and s["refusals"] < 1:
                raise GameError("You have no refusal tokens left.")
            return {"stance": stance}
        if game == "insurance":
            choice = str(values.get("choice", ""))
            costs = {"strengthen": 8, "extract": 0, "buy": 8, "underwrite": 0, "sabotage": 0}
            if choice not in costs:
                raise GameError("Choose a market action.")
            if s["liquid"] < costs[choice]:
                raise GameError("You do not have enough liquid wealth for that action.")
            return {"choice": choice}
        choice = str(values.get("choice", ""))
        costs = {"ambition": 10, "protect": 6, "support": 6, "challenge": 8, "conserve": 0}
        if choice not in costs:
            raise GameError("Choose a reputation action.")
        if s["reputation"] < costs[choice]:
            raise GameError("You do not have enough reputation for that action.")
        target = self._target(room, player, values.get("target"), choice in {"support", "challenge"})
        return {"choice": choice, "target": target}

    @staticmethod
    def _safe_action(room: Room, player: Player) -> dict[str, Any]:
        if room.game_id == "vault":
            return {"deposit": 0, "useKey": False, "useSeal": False}
        if room.game_id == "burden":
            return {"protected": player.stats["wealth"], "exposed": 0, "transferred": 0, "target": "", "useSeal": False}
        if room.game_id == "chain":
            return {"stance": "pass"}
        if room.game_id == "insurance":
            return {"choice": "strengthen" if player.stats["liquid"] >= 8 else "extract"}
        return {"choice": "conserve", "target": ""}

    def _start_round(self, room: Room) -> None:
        room.round_number += 1
        room.phase = "decision"
        room.result = None
        for player in room.players.values():
            player.action = None

        if room.game_id == "vault":
            category = self.rng.choice(("Flood", "Opportunity", "Tax", "Audit", "Rescue", "Fracture"))
            room.prompt = {"title": category, "subtitle": "Category known · exact severity hidden"}
            room.hidden = {"severity": self.rng.randint(8, 18)}
        elif room.game_id == "burden":
            condition = self.rng.choice(("Stability", "Expansion", "Panic", "Corrosion", "Exposure"))
            room.prompt = {"title": condition, "subtitle": "Allocate every unit before collective pressure is revealed"}
            room.hidden = {"swing": self.rng.random()}
        elif room.game_id == "chain":
            risk = min(82, 10 + room.round_number * 8)
            room.prompt = {"title": f"Charge {room.round_number}", "subtitle": "Value and rupture risk are both rising"}
            room.hidden = {"risk": risk, "roll": self.rng.randint(1, 100)}
            room.data["hints"] = {
                p.id: f"Your clue estimates rupture risk near {max(5, min(95, risk + self.rng.randint(-18, 18)))}%."
                for p in room.players.values()
            }
        elif room.game_id == "insurance":
            threat = self.rng.choice(("Liquidity Failure", "Structural Damage", "Reputation Shock"))
            room.prompt = {"title": threat, "subtitle": "Forecast only · collective actions determine probability"}
            room.hidden = {"baseRisk": self.rng.randint(28, 48), "roll": self.rng.randint(1, 100)}
        else:
            crisis = self.rng.choice(("Public Promise", "Evidence Leak", "Coalition Vote", "Trust Crisis", "Final Mandate"))
            room.prompt = {"title": crisis, "subtitle": "Reputation spent now becomes influence for the room"}
            room.hidden = {"favored": self.rng.choice(("ambition", "protect", "support", "challenge"))}
        room.version += 1

    def _resolve(self, room: Room, forced: bool) -> None:
        before = {p.id: deepcopy(p.stats) for p in room.players.values()}
        if room.game_id == "vault":
            title, detail, pressure = self._resolve_vault(room)
        elif room.game_id == "burden":
            title, detail, pressure = self._resolve_burden(room)
        elif room.game_id == "chain":
            title, detail, pressure = self._resolve_chain(room)
        elif room.game_id == "insurance":
            title, detail, pressure = self._resolve_insurance(room)
        else:
            title, detail, pressure = self._resolve_reputation(room)
        room.result = {
            "title": title,
            "detail": detail,
            "pressure": pressure,
            "forced": forced,
            "changes": [
                {"playerId": p.id, "summary": self._change_summary(room.game_id, before[p.id], p.stats)}
                for p in room.players.values()
            ],
        }
        room.phase = "results"
        room.version += 1

    def _resolve_vault(self, room: Room) -> tuple[str, str, str]:
        for player in room.players.values():
            a, s = player.action.values, player.stats
            if a["useKey"]:
                withdrawal = min(s["vault"], max(1, round(s["vault"] * 0.2)))
                s["vault"] -= withdrawal
                s["liquid"] += withdrawal
                s["keys"] -= 1
            s["liquid"] -= a["deposit"]
            s["vault"] += a["deposit"]
            if a["useSeal"]:
                s["seals"] -= 1
        total_liquid = sum(p.stats["liquid"] for p in room.players.values())
        total_wealth = sum(p.stats["liquid"] + p.stats["vault"] for p in room.players.values()) or 1
        ratio = total_liquid / total_wealth
        pressure = "scarce" if ratio < .30 else "exposed" if ratio > .70 else "balanced"
        category, severity = room.prompt["title"], room.hidden["severity"]
        detail = ""
        for player in room.players.values():
            a, s = player.action.values, player.stats
            sealed = a["useSeal"]
            if category == "Flood":
                rate = .20 + severity / 100 + (.10 if pressure == "exposed" else 0)
                s["liquid"] -= round(s["liquid"] * (min(rate, .05) if sealed else rate))
                detail = f"The flood removed {round(rate * 100)}% of unsealed liquid wealth."
            elif category == "Opportunity":
                rate = (.18 + severity / 100) * (.5 if pressure == "scarce" else 1)
                s["liquid"] += round(s["liquid"] * rate)
                detail = f"Liquid wealth grew by {round(rate * 100)}%."
            elif category == "Tax":
                rate = .06 + severity / 200 + (.05 if pressure == "scarce" else 0)
                tax = round((s["liquid"] + s["vault"]) * rate)
                liquid_tax = min(s["liquid"], 0 if sealed else tax)
                s["liquid"] -= liquid_tax
                s["vault"] = max(0, s["vault"] - (tax - liquid_tax))
                detail = f"A {round(rate * 100)}% wealth tax was collected, liquid first."
            elif category == "Audit":
                rate = .10 + severity / 200
                s["vault"] -= round(s["vault"] * rate)
                detail = f"The audit removed {round(rate * 100)}% of vault holdings."
            elif category == "Rescue":
                if pressure == "scarce":
                    s["vault"] -= round(s["vault"] * .12)
                    s["penalties"] += 5
                    detail = "Liquidity scarcity damaged every vault and added a collapse penalty."
                else:
                    s["rescueBonus"] += 8 if s["liquid"] >= 40 else 3
                    detail = "Adequate room liquidity earned rescue bonuses."
            else:
                rate = .12 + severity / 100
                s["vault"] -= round(s["vault"] * rate)
                detail = f"The fracture removed {round(rate * 100)}% of vault holdings."
        return category, f"{detail} Room liquidity was {round(ratio * 100)}%.", pressure

    def _resolve_burden(self, room: Room) -> tuple[str, str, str]:
        total_wealth = sum(p.stats["wealth"] for p in room.players.values()) or 1
        total_exposed = sum(p.action.values["exposed"] for p in room.players.values())
        ratio = total_exposed / total_wealth
        if ratio <= .30:
            rate = .04
        elif ratio <= .60:
            rate = .18
        elif ratio <= .80:
            rate = .35 if room.hidden["swing"] >= .5 else -.25
        else:
            rate = -.45 if room.hidden["swing"] < .70 else .10
        condition = room.prompt["title"]
        rate += {"Stability": .02, "Expansion": .05, "Panic": -.08, "Corrosion": -.04, "Exposure": -.06}[condition]
        incoming = {p.id: 0 for p in room.players.values()}
        collapse = rate < 0
        for player in room.players.values():
            a, s = player.action.values, player.stats
            if a["transferred"]:
                incoming[a["target"]] += a["transferred"]
                if collapse:
                    s["supportBonus"] += 5
            exposed_value = round(a["exposed"] * (1 + rate))
            if a["useSeal"]:
                exposed_value = max(exposed_value, round(a["exposed"] * .70))
                s["seals"] -= 1
            s["wealth"] = round(a["protected"] * .97) + max(0, exposed_value)
        for player in room.players.values():
            player.stats["wealth"] += incoming[player.id]
            if player.stats["wealth"] <= 0:
                player.stats["wealth"] = 15
                player.stats["debtScars"] += 1
        pressure = "calm" if ratio <= .30 else "growth" if ratio <= .60 else "collapse" if collapse else "volatile"
        return condition, f"Room exposure reached {round(ratio * 100)}%; exposed wealth changed {round(rate * 100):+d}% while protected wealth decayed 3%.", pressure

    def _resolve_chain(self, room: Room) -> tuple[str, str, str]:
        stances = [p.action.values["stance"] for p in room.players.values()]
        carriers = stances.count("carry")
        risk = min(95, room.hidden["risk"] + carriers * 5)
        rupture = room.hidden["roll"] <= risk
        if rupture:
            room.data["ruptures"] = room.data.get("ruptures", 0) + 1
        growth = 5 + room.round_number * 3
        for player in room.players.values():
            stance, s = player.action.values["stance"], player.stats
            if stance == "carry":
                s["unsecured"] += growth
                if rupture:
                    s["unsecured"] = 0
                    s["secured"] = round(s["secured"] * .75)
                    s["courage"] += 1
                else:
                    secured_now = round(s["unsecured"] * .70)
                    s["secured"] += secured_now
                    s["unsecured"] -= secured_now
            elif stance == "pass":
                s["secured"] += round(growth * .70)
                if rupture:
                    s["secured"] = round(s["secured"] * .95)
            elif stance == "refuse":
                s["refusals"] -= 1
            elif stance == "redirect":
                s["secured"] += round(growth * .56)
                if rupture:
                    s["secured"] = round(s["secured"] * .95)
            else:
                s["secured"] += round(growth * .50)
                s["breaker"] += 1
        title = "The Charge ruptured" if rupture else "The chain held"
        detail = f"Rupture risk reached {risk}%. " + ("Carriers lost unsecured value and 25% secured value." if rupture else "Risk takers secured 70% of the growing Charge.")
        return title, detail, "rupture" if rupture else "intact"

    def _resolve_insurance(self, room: Room) -> tuple[str, str, str]:
        choices = [p.action.values["choice"] for p in room.players.values()]
        risk = room.hidden["baseRisk"] - choices.count("strengthen") * 10 + choices.count("extract") * 8 + choices.count("sabotage") * 15
        risk = max(5, min(95, risk))
        disaster = room.hidden["roll"] <= risk
        underwriters = [p for p in room.players.values() if p.action.values["choice"] == "underwrite"]
        for player in room.players.values():
            choice, s = player.action.values["choice"], player.stats
            if choice == "strengthen":
                s["liquid"] -= 8
                s["reliability"] += 2
            elif choice == "extract":
                s["liquid"] += 15
                s["assets"] -= 3
            elif choice == "buy":
                s["liquid"] -= 8
            elif choice == "underwrite":
                s["liquid"] += 12
                s["premiums"] += 12
                s["obligations"] += 20
            else:
                s["liquid"] += 10
                s["reliability"] -= 4
            if disaster:
                loss = 25
                if choice == "buy":
                    loss = 10
                s["assets"] = max(0, s["assets"] - loss)
        if disaster:
            for player in underwriters:
                s = player.stats
                payment = min(s["liquid"], s["obligations"])
                s["liquid"] -= payment
                s["obligations"] -= payment
                if s["obligations"]:
                    s["assets"] = max(0, s["assets"] - 10)
                    s["reliability"] -= 8
                else:
                    s["reliability"] += 5
        else:
            for player in underwriters:
                player.stats["obligations"] = max(0, player.stats["obligations"] - 5)
        title = room.prompt["title"] + (" materialized" if disaster else " was avoided")
        detail = f"Collective behavior moved threat probability to {risk}%. " + ("Claims and correlated obligations were resolved." if disaster else "Policies survived and underwriters retained premiums.")
        return title, detail, "disaster" if disaster else "stable"

    def _resolve_reputation(self, room: Room) -> tuple[str, str, str]:
        costs = {"ambition": 10, "protect": 6, "support": 6, "challenge": 8, "conserve": 0}
        votes: dict[str, int] = {}
        pool = 0
        favored = room.hidden["favored"]
        for player in room.players.values():
            choice, s = player.action.values["choice"], player.stats
            cost = costs[choice]
            s["reputation"] -= cost
            pool += cost
            if choice == "ambition":
                s["ambitions"] += 1
            elif choice == "protect":
                s["keptPromises"] += 1
            elif choice == "support":
                target = player.action.values["target"]
                votes[target] = votes.get(target, 0) + 1
            elif choice == "challenge":
                target = room.players[player.action.values["target"]]
                target.stats["reputation"] = max(0, target.stats["reputation"] - 5)
            else:
                s["reputation"] += 4
            if choice == favored:
                s["alignment"] += 5
        recipient_id = max(votes, key=votes.get) if votes else max(room.players, key=lambda pid: room.players[pid].stats["reputation"])
        room.players[recipient_id].stats["reputation"] += pool
        recipient = room.players[recipient_id].name
        title = room.prompt["title"] + " resolved"
        detail = f"{pool} spent reputation returned to {recipient}, the room’s strongest supported voice. The crisis favored {favored}."
        return title, detail, "redistributed"

    @staticmethod
    def _change_summary(game_id: str, before: dict[str, int], after: dict[str, int]) -> str:
        primary = {
            "vault": ("liquid", "vault"),
            "burden": ("wealth", "supportBonus"),
            "chain": ("secured", "courage"),
            "insurance": ("assets", "liquid"),
            "reputation": ("reputation", "alignment"),
        }[game_id]
        parts = []
        for key in primary:
            delta = after[key] - before[key]
            parts.append(f"{key}: {delta:+d}")
        return " · ".join(parts)

    def public_state(self, code: str, viewer_id: str) -> dict[str, Any]:
        with self.lock:
            room = self._room(code)
            viewer = self._player(room, viewer_id)
            players = list(room.players.values())
            if room.phase == "finished":
                players.sort(key=lambda p: (-p.score(room.game_id), p.name.casefold()))
            return {
                "code": room.code,
                "gameId": room.game_id,
                "gameName": GAME_CONFIG[room.game_id]["name"],
                "phase": room.phase,
                "round": room.round_number,
                "totalRounds": GAME_CONFIG[room.game_id]["rounds"],
                "prompt": room.prompt,
                "result": room.result,
                "version": room.version,
                "hostId": room.host_id,
                "viewerId": viewer.id,
                "viewerHasActed": viewer.action is not None,
                "viewerHint": room.data.get("hints", {}).get(viewer.id) if room.game_id == "chain" else None,
                "players": [self._public_player(room, p, viewer.id) for p in players],
            }

    def _public_player(self, room: Room, player: Player, viewer_id: str) -> dict[str, Any]:
        own = player.id == viewer_id
        stats = deepcopy(player.stats)
        if room.game_id == "vault" and not own and room.phase != "finished":
            value = stats.pop("vault")
            stats["vaultRange"] = f"{(value // 25) * 25}-{(value // 25) * 25 + 24}"
            for key in ("keys", "seals", "penalties", "rescueBonus"):
                stats.pop(key, None)
        return {
            "id": player.id,
            "name": player.name,
            "acted": player.action is not None,
            "stats": stats,
            "score": player.score(room.game_id) if room.phase == "finished" else None,
        }

