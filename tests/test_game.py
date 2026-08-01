import unittest
from random import Random

from backend.game import GAME_CONFIG, GameError, GameStore


class GameStoreTests(unittest.TestCase):
    def make_room(self, game_id="vault"):
        store = GameStore(Random(7))
        room, host = store.create_room("Host", game_id)
        _, guest = store.join_room(room.code, "Guest")
        return store, room, host, guest

    @staticmethod
    def action_for(game_id, player):
        if game_id == "vault":
            return {"deposit": min(5, player.stats["liquid"]), "useKey": False, "useSeal": False}
        if game_id == "burden":
            return {"protected": player.stats["wealth"], "exposed": 0, "transferred": 0, "target": "", "useSeal": False}
        if game_id == "chain":
            return {"stance": "pass"}
        if game_id == "insurance":
            return {"choice": "strengthen"}
        return {"choice": "conserve", "target": ""}

    def test_every_game_runs_to_final_scores(self):
        for game_id, config in GAME_CONFIG.items():
            with self.subTest(game_id=game_id):
                store, room, host, guest = self.make_room(game_id)
                store.start(room.code, host.id)
                for round_number in range(1, config["rounds"] + 1):
                    if room.phase == "finished":
                        break
                    store.submit_action(room.code, host.id, self.action_for(game_id, host), f"h{round_number}")
                    store.submit_action(room.code, guest.id, self.action_for(game_id, guest), f"g{round_number}")
                    self.assertEqual(room.phase, "results")
                    store.next_round(room.code, host.id)
                self.assertEqual(room.phase, "finished")
                final = store.public_state(room.code, host.id)
                self.assertTrue(all(player["score"] is not None for player in final["players"]))

    def test_action_is_idempotent_and_only_once(self):
        store, room, host, _ = self.make_room()
        store.start(room.code, host.id)
        values = self.action_for("vault", host)
        store.submit_action(room.code, host.id, values, "same")
        store.submit_action(room.code, host.id, values, "same")
        with self.assertRaises(GameError):
            store.submit_action(room.code, host.id, values, "different")

    def test_private_vault_value_is_hidden(self):
        store, room, host, guest = self.make_room()
        store.start(room.code, host.id)
        state = store.public_state(room.code, host.id)
        other = next(player for player in state["players"] if player["id"] == guest.id)
        self.assertNotIn("vault", other["stats"])
        self.assertIn("vaultRange", other["stats"])

    def test_only_host_can_start(self):
        store, room, _, guest = self.make_room()
        with self.assertRaises(GameError):
            store.start(room.code, guest.id)

    def test_invalid_game_is_rejected(self):
        store = GameStore(Random(1))
        with self.assertRaises(GameError):
            store.create_room("Host", "unknown")


if __name__ == "__main__":
    unittest.main()
