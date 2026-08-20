import io
import json
import logging
import unittest

from backend.infrastructure.observability.logging import ContextFilter, JsonFormatter, bind_context


class ObservabilityTests(unittest.TestCase):
    def test_json_logs_include_safe_correlation_context(self) -> None:
        output = io.StringIO()
        handler = logging.StreamHandler(output)
        handler.addFilter(ContextFilter())
        handler.setFormatter(JsonFormatter())
        logger = logging.getLogger("test.observability")
        logger.handlers = [handler]
        logger.propagate = False
        logger.setLevel(logging.INFO)
        binding = bind_context("request-123", "ABCDE", "POST /api/rooms/ABCDE/start")
        try:
            logger.info(
                "Request completed",
                extra={"event": "http.request.completed", "http_status": 200, "player_ref": "a1b2c3d4e5f6"},
            )
        finally:
            binding.reset()

        record = json.loads(output.getvalue())
        self.assertEqual(record["request_id"], "request-123")
        self.assertEqual(record["room_code"], "ABCDE")
        self.assertEqual(record["http_status"], 200)
        self.assertEqual(record["player_ref"], "a1b2c3d4e5f6")
        self.assertNotIn("playerId", record)


if __name__ == "__main__":
    unittest.main()
