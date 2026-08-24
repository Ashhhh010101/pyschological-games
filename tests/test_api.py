import argparse
import unittest
from random import Random
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from backend.game import GAME_CONFIG, GameStore
from backend.server import create_app, main, valid_port
from backend.settings import Settings


class FastApiTests(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(create_app(GameStore(Random(11))))
        self.client.__enter__()

    def tearDown(self):
        self.client.__exit__(None, None, None)

    def test_health_docs_and_frontend_are_served(self):
        health = self.client.get("/api/health")
        self.assertEqual(health.status_code, 200)
        self.assertEqual(set(health.json()["games"]), set(GAME_CONFIG))
        self.assertIn("Psychological Games", self.client.get("/").text)
        self.assertEqual(self.client.get("/docs").status_code, 200)
        self.assertEqual(health.headers["cache-control"], "no-store")
        self.assertEqual(health.headers["x-content-type-options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", health.headers["content-security-policy"])

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
        self.assertIn("gameId", response.json()["error"]["message"])

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

    def test_all_command_routes_and_games_catalog(self):
        games = self.client.get("/api/games")
        self.assertEqual(len(games.json()), len(GAME_CONFIG))
        created = self.client.post("/api/rooms", json={"name": "Host", "gameId": "vault"}).json()
        guest = self.client.post(f"/api/rooms/{created['code']}/join", json={"name": "Guest"}).json()
        self.client.post(f"/api/rooms/{created['code']}/start", json={"playerId": created["playerId"]})
        action = {"deposit": 0, "useKey": False, "useSeal": False}
        for identity, key in ((created["playerId"], "host"), (guest["playerId"], "guest")):
            response = self.client.post(
                f"/api/rooms/{created['code']}/actions",
                json={"playerId": identity, "values": action, "idempotencyKey": key},
            )
            self.assertEqual(response.status_code, 200)
        advanced = self.client.post(
            f"/api/rooms/{created['code']}/next",
            json={"playerId": created["playerId"]},
        )
        self.assertEqual(advanced.status_code, 200)

    def test_websocket_rejects_invalid_session(self):
        with (
            self.assertRaises(WebSocketDisconnect),
            self.client.websocket_connect("/api/rooms/NOPE/ws?playerId=invalid"),
        ):
            pass


class ServerUtilityTests(unittest.TestCase):
    def test_port_validation_and_main(self):
        self.assertEqual(valid_port("8000"), 8000)
        for value in ("bad", "0", "65536"):
            with self.assertRaises(argparse.ArgumentTypeError):
                valid_port(value)
        settings = Settings(_env_file=None, app_env="test", host="localhost", port=9000)
        with (
            patch("backend.server.get_settings", return_value=settings),
            patch("backend.server.uvicorn.run") as run,
            patch(
                "backend.server.argparse.ArgumentParser.parse_args",
                return_value=Mock(host="x", port=1),
            ),
        ):
            main()
        run.assert_called_once()


if __name__ == "__main__":
    unittest.main()
