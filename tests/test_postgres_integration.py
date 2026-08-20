import asyncio
import os
import unittest

from sqlalchemy import func, select

from backend.application.room_service import RoomService
from backend.application.session_service import SessionService
from backend.domain.exceptions import ApplicationError
from backend.infrastructure.database.models import ResultRecord
from backend.infrastructure.database.repositories.sqlalchemy_room_repository import SQLAlchemyRoomRepository
from backend.infrastructure.database.session import create_database
from backend.settings import Settings

TEST_DATABASE_URL = os.getenv("TEST_DATABASE_URL")


@unittest.skipUnless(TEST_DATABASE_URL, "TEST_DATABASE_URL is required for PostgreSQL integration tests")
class PostgreSQLIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        settings = Settings(
            app_env="test",
            database_url=TEST_DATABASE_URL or "sqlite+aiosqlite:///:memory:",
            rate_limit_enabled=False,
        )
        self.engine, self.sessions = create_database(settings)
        self.repository = SQLAlchemyRoomRepository(
            self.engine,
            self.sessions,
            settings.room_idle_ttl_seconds,
            auto_create=False,
        )
        self.service = RoomService(self.repository, SessionService(settings.session_ttl_seconds))

    async def asyncTearDown(self) -> None:
        await self.repository.close()

    async def test_row_lock_allows_only_one_round_resolution(self) -> None:
        created = await self.service.create_room("Postgres Host", "vault")
        await self.service.join_room(created["code"], "Postgres Guest")
        await self.service.start(created["code"], created["playerId"], "pg-start")

        outcomes = await asyncio.gather(
            self.service.force_resolve(created["code"], created["playerId"], "pg-resolve-a"),
            self.service.force_resolve(created["code"], created["playerId"], "pg-resolve-b"),
            return_exceptions=True,
        )
        self.assertEqual(sum(isinstance(value, dict) for value in outcomes), 1)
        self.assertEqual(sum(isinstance(value, ApplicationError) for value in outcomes), 1)
        async with self.sessions() as session:
            result_count = await session.scalar(
                select(func.count()).select_from(ResultRecord).where(ResultRecord.room_code == created["code"])
            )
        self.assertEqual(result_count, 1)


if __name__ == "__main__":
    unittest.main()
