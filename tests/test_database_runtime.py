import tempfile
import unittest
from pathlib import Path

from sqlalchemy import text

from backend.application.room_service import RoomService
from backend.application.session_service import SessionService
from backend.infrastructure.database.repositories.sqlalchemy_room_repository import SQLAlchemyRoomRepository
from backend.infrastructure.database.session import create_database
from backend.migrate import wait_for_database
from backend.settings import Settings


class RuntimeDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def test_sqlite_file_enables_durability_and_integrity_pragmas(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory, "runtime.db").as_posix()
            settings = Settings(
                _env_file=None,
                app_env="test",
                database_url=f"sqlite+aiosqlite:///{database_path}",
                sqlite_busy_timeout_ms=4321,
            )
            engine, _ = create_database(settings)
            try:
                async with engine.connect() as connection:
                    foreign_keys = await connection.scalar(text("PRAGMA foreign_keys"))
                    journal_mode = await connection.scalar(text("PRAGMA journal_mode"))
                    busy_timeout = await connection.scalar(text("PRAGMA busy_timeout"))
                self.assertEqual(foreign_keys, 1)
                self.assertEqual(str(journal_mode).lower(), "wal")
                self.assertEqual(busy_timeout, 4321)
            finally:
                await engine.dispose()

    async def test_migration_waiter_uses_the_selected_sqlite_backend(self) -> None:
        settings = Settings(
            _env_file=None,
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            database_connect_attempts=1,
        )
        await wait_for_database(settings)

    async def test_sqlite_room_and_session_survive_engine_restart(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            database_path = Path(directory, "restart.db").as_posix()
            settings = Settings(
                _env_file=None,
                app_env="test",
                database_url=f"sqlite+aiosqlite:///{database_path}",
                room_idle_ttl_seconds=60,
                session_ttl_seconds=300,
            )
            first_engine, first_sessions = create_database(settings)
            first_repository = SQLAlchemyRoomRepository(
                first_engine,
                first_sessions,
                settings.room_idle_ttl_seconds,
            )
            await first_repository.initialize()
            first_service = RoomService(first_repository, SessionService(settings.session_ttl_seconds))
            created = await first_service.create_room("Persistent Host", "vault")
            await first_repository.close()

            second_engine, second_sessions = create_database(settings)
            second_repository = SQLAlchemyRoomRepository(
                second_engine,
                second_sessions,
                settings.room_idle_ttl_seconds,
            )
            await second_repository.initialize()
            try:
                state = await RoomService(
                    second_repository,
                    SessionService(settings.session_ttl_seconds),
                ).public_state(created["code"], created["playerId"])
                self.assertEqual(state["code"], created["code"])
                self.assertEqual(state["phase"], "lobby")
            finally:
                await second_repository.close()


if __name__ == "__main__":
    unittest.main()
