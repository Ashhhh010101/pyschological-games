from __future__ import annotations

import secrets
import string
from copy import deepcopy
from random import Random
from threading import RLock
from typing import Any

from backend.config import GAME_CONFIG, MAX_PLAYERS, MIN_PLAYERS, GameId
from backend.models import Action, Player, Room


class GameError(Exception):
    """A validation error that is safe to return to a client."""

    status_code = 400


class GameNotFoundError(GameError):
    """The requested room or player does not exist."""

    status_code = 404


class GamePermissionError(GameError):
    """The current player is not authorized for an operation."""

    status_code = 403


class GameConflictError(GameError):
    """The requested operation conflicts with the current room state."""

    status_code = 409


class GameStore:
    """Thread-safe room store with server-authoritative rules for all game modes."""

    def __init__(self, rng: Random | None = None) -> None:
        self.rooms: dict[str, Room] = {}
        self.rng = rng or Random()
        self.lock = RLock()

    @property
    def room_count(self) -> int:
        """Return a synchronized room count for diagnostics."""
        with self.lock:
            return len(self.rooms)

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
        if not isinstance(name, str):
            raise GameError("Name must be text.")
        clean = " ".join(name.strip().split())
        if not 1 <= len(clean) <= 24:
            raise GameError("Name must contain 1 to 24 characters.")
        return clean

    @staticmethod
    def _new_stats(game_id: GameId) -> dict[str, int]:
        return deepcopy(GAME_CONFIG[game_id]["stats"])

    def _room(self, code: str) -> Room:
        if not isinstance(code, str):
            raise GameNotFoundError("Room not found.")
        room = self.rooms.get(code.upper())
        if room is None:
            raise GameNotFoundError("Room not found.")
        return room

    @staticmethod
    def _player(room: Room, player_id: str) -> Player:
        player = room.players.get(player_id)
        if player is None:
            raise GameNotFoundError("Player not found in this room.")
        return player

    def create_room(self, name: Any, game_id: Any = "vault") -> tuple[Room, Player]:
        with self.lock:
            selected_value = game_id.lower() if isinstance(game_id, str) else ""
            if selected_value not in GAME_CONFIG:
                raise GameError("Unknown game selection.")
            selected = selected_value
            player = Player(self._player_id(), self._clean_name(name), self._new_stats(selected))
            room = Room(self._room_code(), selected, player.id, {player.id: player})
            self.rooms[room.code] = room
            return room, player

    def join_room(self, code: str, name: Any) -> tuple[Room, Player]:
        with self.lock:
            room = self._room(code)
            if room.phase != "lobby":
                raise GameConflictError("This game has already started.")
            if len(room.players) >= MAX_PLAYERS:
                raise GameConflictError("This room is full.")
            clean_name = self._clean_name(name)
            if any(p.name.casefold() == clean_name.casefold() for p in room.players.values()):
                raise GameConflictError("That name is already in use in this room.")
            player = Player(self._player_id(), clean_name, self._new_stats(room.game_id))
            room.players[player.id] = player
            room.version += 1
            return room, player

    def start(self, code: str, player_id: str) -> Room:
        with self.lock:
            room = self._room(code)
            self._require_host(room, player_id)
            if room.phase != "lobby":
                raise GameConflictError("The game has already started.")
            if len(room.players) < MIN_PLAYERS:
                raise GameConflictError(f"At least {MIN_PLAYERS} players are required.")
            self._start_round(room)
            return room

    def next_round(self, code: str, player_id: str) -> Room:
        with self.lock:
            room = self._room(code)
            self._require_host(room, player_id)
            if room.phase != "results":
                raise GameConflictError("The current round is not ready to advance.")
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
                raise GameConflictError("Actions are closed for this round.")
            if not isinstance(idempotency_key, str):
                raise GameError("An idempotency key is required.")
            key = idempotency_key.strip()
            if not 1 <= len(key) <= 128:
                raise GameError("Idempotency key must contain 1 to 128 characters.")
            if player.action:
                if player.action.idempotency_key == key:
                    return room
                raise GameConflictError("You already submitted an action this round.")
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
                raise GameConflictError("This round cannot be resolved now.")
            for player in room.players.values():
                if player.action is None:
                    player.action = Action(self._safe_action(room, player), "afk-safe-action")
            self._resolve(room, forced=True)
            return room

    @staticmethod
    def _require_host(room: Room, player_id: str) -> None:
        if room.host_id != player_id:
            raise GamePermissionError("Only the room host can do that.")

    @staticmethod
    def _integer(value: Any, label: str, low: int, high: int) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise GameError(f"{label} must be a whole number.")
        if not low <= value <= high:
            raise GameError(f"{label} must be between {low} and {high}.")
        return int(value)

    @staticmethod
    def _boolean(value: Any, label: str) -> bool:
        if not isinstance(value, bool):
            raise GameError(f"{label} must be true or false.")
        return value

    @staticmethod
    def _action_values(player: Player) -> dict[str, Any]:
        if player.action is None:
            raise RuntimeError("Cannot resolve a room with missing player actions.")
        return player.action.values

    @staticmethod
    def _prompt_title(room: Room) -> str:
        if room.prompt is None:
            raise RuntimeError("Cannot resolve a room without a round prompt.")
        return room.prompt["title"]

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
                "useKey": self._boolean(values.get("useKey"), "Use key") and s["keys"] > 0,
                "useSeal": self._boolean(values.get("useSeal"), "Use seal") and s["seals"] > 0,
            }
        if game == "burden":
            protected = self._integer(values.get("protected"), "Protected wealth", 0, s["wealth"])
            exposed = self._integer(values.get("exposed"), "Exposed wealth", 0, s["wealth"])
            transferred = self._integer(values.get("transferred"), "Transferred wealth", 0, s["wealth"])
            if protected + exposed + transferred != s["wealth"]:
                raise GameError("Protected, exposed, and transferred amounts must equal your wealth.")
            target = self._target(room, player, values.get("target"), transferred > 0)
            return {
                "protected": protected,
                "exposed": exposed,
                "transferred": transferred,
                "target": target,
                "useSeal": self._boolean(values.get("useSeal"), "Use seal") and s["seals"] > 0,
            }
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
            crisis = self.rng.choice(
                ("Public Promise", "Evidence Leak", "Coalition Vote", "Trust Crisis", "Final Mandate")
            )
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
            a, s = self._action_values(player), player.stats
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
        pressure = "scarce" if ratio < 0.30 else "exposed" if ratio > 0.70 else "balanced"
        category, severity = self._prompt_title(room), room.hidden["severity"]
        detail = ""
        for player in room.players.values():
            a, s = self._action_values(player), player.stats
            sealed = a["useSeal"]
            if category == "Flood":
                rate = 0.20 + severity / 100 + (0.10 if pressure == "exposed" else 0)
                s["liquid"] -= round(s["liquid"] * (min(rate, 0.05) if sealed else rate))
                detail = f"The flood removed {round(rate * 100)}% of unsealed liquid wealth."
            elif category == "Opportunity":
                rate = (0.18 + severity / 100) * (0.5 if pressure == "scarce" else 1)
                s["liquid"] += round(s["liquid"] * rate)
                detail = f"Liquid wealth grew by {round(rate * 100)}%."
            elif category == "Tax":
                rate = 0.06 + severity / 200 + (0.05 if pressure == "scarce" else 0)
                tax = round((s["liquid"] + s["vault"]) * rate)
                liquid_tax = min(s["liquid"], 0 if sealed else tax)
                s["liquid"] -= liquid_tax
                s["vault"] = max(0, s["vault"] - (tax - liquid_tax))
                detail = f"A {round(rate * 100)}% wealth tax was collected, liquid first."
            elif category == "Audit":
                rate = 0.10 + severity / 200
                s["vault"] -= round(s["vault"] * rate)
                detail = f"The audit removed {round(rate * 100)}% of vault holdings."
            elif category == "Rescue":
                if pressure == "scarce":
                    s["vault"] -= round(s["vault"] * 0.12)
                    s["penalties"] += 5
                    detail = "Liquidity scarcity damaged every vault and added a collapse penalty."
                else:
                    s["rescueBonus"] += 8 if s["liquid"] >= 40 else 3
                    detail = "Adequate room liquidity earned rescue bonuses."
            else:
                rate = 0.12 + severity / 100
                s["vault"] -= round(s["vault"] * rate)
                detail = f"The fracture removed {round(rate * 100)}% of vault holdings."
        return category, f"{detail} Room liquidity was {round(ratio * 100)}%.", pressure

    def _resolve_burden(self, room: Room) -> tuple[str, str, str]:
        total_wealth = sum(p.stats["wealth"] for p in room.players.values()) or 1
        total_exposed = sum(self._action_values(player)["exposed"] for player in room.players.values())
        ratio = total_exposed / total_wealth
        if ratio <= 0.30:
            rate = 0.04
        elif ratio <= 0.60:
            rate = 0.18
        elif ratio <= 0.80:
            rate = 0.35 if room.hidden["swing"] >= 0.5 else -0.25
        else:
            rate = -0.45 if room.hidden["swing"] < 0.70 else 0.10
        condition = self._prompt_title(room)
        rate += {
            "Stability": 0.02,
            "Expansion": 0.05,
            "Panic": -0.08,
            "Corrosion": -0.04,
            "Exposure": -0.06,
        }[condition]
        incoming = {p.id: 0 for p in room.players.values()}
        collapse = rate < 0
        for player in room.players.values():
            a, s = self._action_values(player), player.stats
            if a["transferred"]:
                incoming[a["target"]] += a["transferred"]
                if collapse:
                    s["supportBonus"] += 5
            exposed_value = round(a["exposed"] * (1 + rate))
            if a["useSeal"]:
                exposed_value = max(exposed_value, round(a["exposed"] * 0.70))
                s["seals"] -= 1
            s["wealth"] = round(a["protected"] * 0.97) + max(0, exposed_value)
        for player in room.players.values():
            player.stats["wealth"] += incoming[player.id]
            if player.stats["wealth"] <= 0:
                player.stats["wealth"] = 15
                player.stats["debtScars"] += 1
        pressure = "calm" if ratio <= 0.30 else "growth" if ratio <= 0.60 else "collapse" if collapse else "volatile"
        detail = (
            f"Room exposure reached {round(ratio * 100)}%; exposed wealth changed "
            f"{round(rate * 100):+d}% while protected wealth decayed 3%."
        )
        return condition, detail, pressure

    def _resolve_chain(self, room: Room) -> tuple[str, str, str]:
        stances = [self._action_values(player)["stance"] for player in room.players.values()]
        carriers = stances.count("carry")
        risk = min(95, room.hidden["risk"] + carriers * 5)
        rupture = room.hidden["roll"] <= risk
        if rupture:
            room.data["ruptures"] = room.data.get("ruptures", 0) + 1
        growth = 5 + room.round_number * 3
        for player in room.players.values():
            stance, s = self._action_values(player)["stance"], player.stats
            if stance == "carry":
                s["unsecured"] += growth
                if rupture:
                    s["unsecured"] = 0
                    s["secured"] = round(s["secured"] * 0.75)
                    s["courage"] += 1
                else:
                    secured_now = round(s["unsecured"] * 0.70)
                    s["secured"] += secured_now
                    s["unsecured"] -= secured_now
            elif stance == "pass":
                s["secured"] += round(growth * 0.70)
                if rupture:
                    s["secured"] = round(s["secured"] * 0.95)
            elif stance == "refuse":
                s["refusals"] -= 1
            elif stance == "redirect":
                s["secured"] += round(growth * 0.56)
                if rupture:
                    s["secured"] = round(s["secured"] * 0.95)
            else:
                s["secured"] += round(growth * 0.50)
                s["breaker"] += 1
        title = "The Charge ruptured" if rupture else "The chain held"
        outcome = (
            "Carriers lost unsecured value and 25% secured value."
            if rupture
            else "Risk takers secured 70% of the growing Charge."
        )
        detail = f"Rupture risk reached {risk}%. {outcome}"
        return title, detail, "rupture" if rupture else "intact"

    def _resolve_insurance(self, room: Room) -> tuple[str, str, str]:
        choices = [self._action_values(player)["choice"] for player in room.players.values()]
        risk = (
            room.hidden["baseRisk"]
            - choices.count("strengthen") * 10
            + choices.count("extract") * 8
            + choices.count("sabotage") * 15
        )
        risk = max(5, min(95, risk))
        disaster = room.hidden["roll"] <= risk
        underwriters = [
            player for player in room.players.values() if self._action_values(player)["choice"] == "underwrite"
        ]
        for player in room.players.values():
            choice, s = self._action_values(player)["choice"], player.stats
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
        title = self._prompt_title(room) + (" materialized" if disaster else " was avoided")
        outcome = (
            "Claims and correlated obligations were resolved."
            if disaster
            else "Policies survived and underwriters retained premiums."
        )
        detail = f"Collective behavior moved threat probability to {risk}%. {outcome}"
        return title, detail, "disaster" if disaster else "stable"

    def _resolve_reputation(self, room: Room) -> tuple[str, str, str]:
        costs = {"ambition": 10, "protect": 6, "support": 6, "challenge": 8, "conserve": 0}
        votes: dict[str, int] = {}
        pool = 0
        favored = room.hidden["favored"]
        for player in room.players.values():
            action = self._action_values(player)
            choice, s = action["choice"], player.stats
            cost = costs[choice]
            s["reputation"] -= cost
            pool += cost
            if choice == "ambition":
                s["ambitions"] += 1
            elif choice == "protect":
                s["keptPromises"] += 1
            elif choice == "support":
                target = action["target"]
                votes[target] = votes.get(target, 0) + 1
            elif choice == "challenge":
                target = room.players[action["target"]]
                target.stats["reputation"] = max(0, target.stats["reputation"] - 5)
            else:
                s["reputation"] += 4
            if choice == favored:
                s["alignment"] += 5
        recipient_id = (
            max(votes, key=lambda player_id: votes[player_id])
            if votes
            else max(room.players, key=lambda player_id: room.players[player_id].stats["reputation"])
        )
        room.players[recipient_id].stats["reputation"] += pool
        recipient = room.players[recipient_id].name
        title = self._prompt_title(room) + " resolved"
        detail = (
            f"{pool} spent reputation returned to {recipient}, the room’s strongest supported voice. "
            f"The crisis favored {favored}."
        )
        return title, detail, "redistributed"

    @staticmethod
    def _change_summary(game_id: GameId, before: dict[str, int], after: dict[str, int]) -> str:
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
        stats: dict[str, int | str] = dict(player.stats)
        if room.game_id == "vault" and not own and room.phase != "finished":
            value = stats.pop("vault")
            if not isinstance(value, int):
                raise RuntimeError("Vault state must be numeric.")
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
