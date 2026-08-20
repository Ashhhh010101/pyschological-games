import unittest

from fastapi.testclient import TestClient

from backend.server import create_app
from backend.settings import Settings


class PersistentApiIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        settings = Settings(
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            rate_limit_enabled=False,
            payload_max_bytes=1024,
        )
        self.client = TestClient(create_app(runtime_settings=settings))
        self.client.__enter__()

    def tearDown(self) -> None:
        self.client.__exit__(None, None, None)

    def test_secure_sessions_readiness_and_viewer_specific_websocket_fanout(self) -> None:
        ready = self.client.get("/api/ready", headers={"X-Request-ID": "integration-check"})
        self.assertEqual(ready.status_code, 200)
        self.assertEqual(ready.headers["x-request-id"], "integration-check")
        host = self.client.post("/api/rooms", json={"name": "Host", "gameId": "vault"}).json()
        guest = self.client.post(f"/api/rooms/{host['code']}/join", json={"name": "Guest"}).json()

        with (
            self.client.websocket_connect(f"/api/rooms/{host['code']}/ws?playerId={host['playerId']}") as host_socket,
            self.client.websocket_connect(f"/api/rooms/{host['code']}/ws?playerId={guest['playerId']}") as guest_socket,
        ):
            host_initial = host_socket.receive_json()
            guest_initial = guest_socket.receive_json()
            self.assertNotEqual(host_initial["viewerId"], host["playerId"])
            self.assertNotEqual(guest_initial["viewerId"], guest["playerId"])

            response = self.client.post(
                f"/api/rooms/{host['code']}/start",
                json={"playerId": host["playerId"], "idempotencyKey": "start-api-1"},
            )
            self.assertEqual(response.status_code, 200)
            self.assertEqual(host_socket.receive_json()["phase"], "decision")
            self.assertEqual(guest_socket.receive_json()["phase"], "decision")

        invalid = self.client.get(f"/api/rooms/{host['code']}?playerId=invalid")
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.json()["error"]["code"], "UNAUTHORIZED_PLAYER")

    def test_oversized_payload_is_rejected_before_json_parsing(self) -> None:
        response = self.client.post(
            "/api/rooms",
            content="x" * 1025,
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(response.status_code, 413)
        self.assertEqual(response.json()["error"]["code"], "PAYLOAD_TOO_LARGE")


if __name__ == "__main__":
    unittest.main()
