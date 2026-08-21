import unittest

from pydantic import ValidationError

from backend.settings import Settings


class SettingsTests(unittest.TestCase):
    def test_defaults_support_local_async_sqlite(self):
        settings = Settings(_env_file=None)
        self.assertTrue(settings.database_url.startswith("sqlite+aiosqlite://"))
        self.assertEqual(settings.database_backend, "sqlite")
        self.assertEqual(settings.port, 8000)

    def test_backend_is_selected_from_database_url(self):
        settings = Settings(
            _env_file=None,
            database_url="postgresql+asyncpg://user:password@database/game",
        )
        self.assertEqual(settings.database_backend, "postgresql")

    def test_origin_and_host_lists_are_normalized(self):
        settings = Settings(
            _env_file=None,
            allowed_origins="https://one.example, https://two.example",
            trusted_hosts="localhost, example.test",
        )
        self.assertEqual(settings.origins, ["https://one.example", "https://two.example"])
        self.assertEqual(settings.hosts, ["localhost", "example.test"])

    def test_rejects_sync_or_unknown_database_driver(self):
        with self.assertRaises(ValidationError):
            Settings(_env_file=None, database_url="postgresql://localhost/game")


if __name__ == "__main__":
    unittest.main()
