import unittest
from random import Random
from unittest.mock import patch

from backend.config import MAX_PLAYERS
from backend.game import GameConflictError, GameError, GameNotFoundError, GamePermissionError, GameStore
from backend.models import Action


class GameEdgeTests(unittest.TestCase):
    def room(self, game_id: str, players: int = 2):
        store = GameStore(Random(4))
        room, host = store.create_room("Host", game_id)
        joined = []
        for number in range(players - 1):
            _, player = store.join_room(room.code, f"Guest {number}")
            joined.append(player)
        store.start(room.code, host.id)
        return store, room, host, joined

    def test_validation_and_state_errors(self) -> None:
        store = GameStore(Random(1))
        self.assertEqual(store.room_count, 0)
        for name in (None, "", "x" * 25):
            with self.assertRaises(GameError):
                store.create_room(name)
        with self.assertRaises(GameNotFoundError):
            store._room(None)  # type: ignore[arg-type]
        room, host = store.create_room("Host")
        with self.assertRaises(GameNotFoundError):
            store._player(room, "missing")
        with self.assertRaises(GameConflictError):
            store.start(room.code, host.id)
        _, guest = store.join_room(room.code, "Guest")
        store.start(room.code, host.id)
        with self.assertRaises(GameConflictError):
            store.join_room(room.code, "Late")
        with self.assertRaises(GameConflictError):
            store.next_round(room.code, host.id)
        with self.assertRaises(GamePermissionError):
            store.force_resolve(room.code, guest.id)
        for key in (None, "", "x" * 129):
            with self.assertRaises(GameError):
                store.submit_action(room.code, host.id, {}, key)
        with self.assertRaises(GameError):
            store.submit_action(room.code, host.id, [], "key")
        with self.assertRaises(GameError):
            store.submit_action(room.code, host.id, {"deposit": 999, "useKey": False, "useSeal": False}, "key")
        with self.assertRaises(RuntimeError):
            store._action_values(host)
        room.prompt = None
        with self.assertRaises(RuntimeError):
            store._prompt_title(room)

    def test_room_capacity_and_code_exhaustion(self) -> None:
        store = GameStore(Random(2))
        room, _ = store.create_room("Host")
        for number in range(MAX_PLAYERS - 1):
            store.join_room(room.code, f"Player {number}")
        with self.assertRaises(GameConflictError):
            store.join_room(room.code, "Full")
        with patch.object(store.rng, "choice", return_value="A"):
            store.rooms["AAAAA"] = room
            with self.assertRaises(GameError):
                store._room_code()

    def test_action_validation_for_every_game(self) -> None:
        store, room, host, guests = self.room("burden")
        guest = guests[0]
        with self.assertRaises(GameError):
            store._validate_action(room, host, {"protected": 1, "exposed": 1, "transferred": 1, "useSeal": False})
        with self.assertRaises(GameError):
            store._validate_action(
                room,
                host,
                {"protected": 0, "exposed": 0, "transferred": 100, "target": host.id, "useSeal": False},
            )
        valid = store._validate_action(
            room,
            host,
            {"protected": 0, "exposed": 0, "transferred": 100, "target": guest.id, "useSeal": True},
        )
        self.assertEqual(valid["target"], guest.id)

        store, room, host, _ = self.room("chain")
        with self.assertRaises(GameError):
            store._validate_action(room, host, {"stance": "unknown"})
        host.stats["refusals"] = 0
        with self.assertRaises(GameError):
            store._validate_action(room, host, {"stance": "refuse"})

        store, room, host, _ = self.room("insurance")
        with self.assertRaises(GameError):
            store._validate_action(room, host, {"choice": "unknown"})
        host.stats["liquid"] = 0
        with self.assertRaises(GameError):
            store._validate_action(room, host, {"choice": "buy"})

        store, room, host, _ = self.room("reputation")
        with self.assertRaises(GameError):
            store._validate_action(room, host, {"choice": "unknown"})
        host.stats["reputation"] = 0
        with self.assertRaises(GameError):
            store._validate_action(room, host, {"choice": "challenge"})

    def test_vault_resolution_categories_and_pressure(self) -> None:
        for category, liquid, use_key, use_seal in (
            ("Flood", 100, True, True),
            ("Opportunity", 0, False, False),
            ("Tax", 0, False, True),
            ("Audit", 50, False, False),
            ("Rescue", 0, False, False),
            ("Rescue", 100, False, False),
            ("Fracture", 50, False, False),
        ):
            with self.subTest(category=category, liquid=liquid):
                store, room, _, _ = self.room("vault")
                room.prompt = {"title": category}
                room.hidden = {"severity": 10}
                for player in room.players.values():
                    player.stats["liquid"] = liquid
                    player.stats["vault"] = 100 - liquid
                    player.action = Action(
                        {"deposit": 0, "useKey": use_key, "useSeal": use_seal},
                        "key",
                    )
                store._resolve_vault(room)

    def test_other_resolvers_cover_all_choices_and_outcomes(self) -> None:
        for exposed, swing in ((0, 0), (50, 0), (70, 0), (70, 1), (100, 0), (100, 1)):
            store, room, _, guests = self.room("burden", 3)
            room.prompt = {"title": "Panic"}
            room.hidden = {"swing": swing}
            players = list(room.players.values())
            for index, player in enumerate(players):
                transferred = 100 if index == 0 else 0
                player.action = Action(
                    {
                        "protected": 0,
                        "exposed": 0 if transferred else exposed,
                        "transferred": transferred,
                        "target": guests[0].id if transferred else "",
                        "useSeal": index == 1,
                    },
                    "key",
                )
            store._resolve_burden(room)

        for rupture in (False, True):
            store, room, _, _ = self.room("chain", 5)
            room.hidden = {"risk": 20, "roll": 1 if rupture else 100}
            stances = ("carry", "pass", "refuse", "redirect", "bank")
            for player, stance in zip(room.players.values(), stances, strict=True):
                player.action = Action({"stance": stance}, "key")
            store._resolve_chain(room)

        for disaster in (False, True):
            store, room, _, _ = self.room("insurance", 5)
            room.prompt = {"title": "Threat"}
            room.hidden = {"baseRisk": 50, "roll": 1 if disaster else 100}
            for player, choice in zip(
                room.players.values(),
                ("strengthen", "extract", "buy", "underwrite", "sabotage"),
                strict=True,
            ):
                player.action = Action({"choice": choice}, "key")
                if choice == "underwrite" and disaster:
                    player.stats["liquid"] = 100
            store._resolve_insurance(room)

        store, room, _, _ = self.room("reputation", 5)
        room.prompt = {"title": "Crisis"}
        room.hidden = {"favored": "ambition"}
        players = list(room.players.values())
        for index, (player, choice) in enumerate(
            zip(players, ("ambition", "protect", "support", "challenge", "conserve"), strict=True)
        ):
            target = players[(index + 1) % len(players)].id
            player.action = Action({"choice": choice, "target": target}, "key")
        store._resolve_reputation(room)

    def test_invalid_private_vault_type(self) -> None:
        store, room, host, guests = self.room("vault")
        guests[0].stats["vault"] = "bad"  # type: ignore[assignment]
        with self.assertRaises(RuntimeError):
            store.public_state(room.code, host.id)

    def test_closed_resolution_and_remaining_loss_branches(self) -> None:
        store, room, host, _ = self.room("vault")
        store.force_resolve(room.code, host.id)
        with self.assertRaises(GameConflictError):
            store.submit_action(room.code, host.id, {}, "closed")
        with self.assertRaises(GameConflictError):
            store.force_resolve(room.code, host.id)

        store, room, _, _ = self.room("burden")
        room.prompt = {"title": "Stability"}
        room.hidden = {"swing": 1.0}
        for player in room.players.values():
            player.action = Action(
                {"protected": 0, "exposed": 100, "transferred": 0, "target": "", "useSeal": False},
                "key",
            )
        store._resolve_burden(room)

        store, room, _, _ = self.room("insurance")
        room.prompt = {"title": "Threat"}
        room.hidden = {"baseRisk": 95, "roll": 1}
        for player in room.players.values():
            player.action = Action({"choice": "underwrite"}, "key")
            player.stats["liquid"] = 0
        store._resolve_insurance(room)


if __name__ == "__main__":
    unittest.main()
