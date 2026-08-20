import unittest
from random import Random

from fastapi.testclient import TestClient

from backend.game import GAME_CONFIG, GameStore
from backend.server import create_app


class FastApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(GameStore(Random(11))))

    def test_health_docs_and_frontend_are_served(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(set(health.json()["games"]), set(GAME_CONFIG))
        self.assertIn("Psychological Games", self.client.get("/").text)
        self.assertEqual(self.client.get("/docs").status_code, 200)

    def test_every_game_can_create_join_start_and_resolve(self):
        for game_id in GAME_CONFIG:
            with self.subTest(game_id=game_id):
                created_response = self.client.post("/api/rooms", json={"name": "Host", "gameId": game_id})
                self.assertEqual(created_response.status_code, 201)
                created = created_response.json()
                joined = self.client.post(f"/api/rooms/{created['code']}/join", json={"name": "Guest"})
                self.assertEqual(joined.status_code, 201)
                payload = {"playerId": created["playerId"]}
                started = self.client.post(f"/api/rooms/{created['code']}/start", json=payload)
                self.assertEqual(started.status_code, 200)
                self.assertEqual(started.json()["gameId"], game_id)
                resolved = self.client.post(f"/api/rooms/{created['code']}/resolve", json=payload)
                self.assertEqual(resolved.status_code, 200)
                self.assertEqual(resolved.json()["phase"], "results")

    def test_validation_errors_are_clear_json(self):
        response = self.client.post("/api/rooms", json={"name": "Host", "gameId": "not-a-game"})
        self.assertEqual(response.status_code, 422)
        self.assertIn("gameId", response.json()["error"])

    def test_domain_errors_use_specific_http_statuses(self):
        missing = self.client.get("/api/rooms/NOPE?playerId=unknown")
        self.assertEqual(missing.status_code, 404)

        created = self.client.post("/api/rooms", json={"name": "Host", "gameId": "vault"}).json()
        joined = self.client.post(f"/api/rooms/{created['code']}/join", json={"name": "Guest"}).json()
        forbidden = self.client.post(
            f"/api/rooms/{created['code']}/start",
            json={"playerId": joined["playerId"]},
        )
        self.assertEqual(forbidden.status_code, 403)

        conflict = self.client.post(
            f"/api/rooms/{created['code']}/start",
            json={"playerId": created["playerId"]},
        )
        self.assertEqual(conflict.status_code, 200)
        repeated = self.client.post(
            f"/api/rooms/{created['code']}/start",
            json={"playerId": created["playerId"]},
        )
        self.assertEqual(repeated.status_code, 409)

    def test_room_websocket_returns_private_room_state(self):
        created = self.client.post("/api/rooms", json={"name": "Host", "gameId": "vault"}).json()
        self.client.post(f"/api/rooms/{created['code']}/join", json={"name": "Guest"})
        with self.client.websocket_connect(f"/api/rooms/{created['code']}/ws?playerId={created['playerId']}") as socket:
            state = socket.receive_json()
            self.assertEqual(state["code"], created["code"])
            self.assertEqual(state["viewerId"], created["playerId"])


if __name__ == "__main__":
    unittest.main()
