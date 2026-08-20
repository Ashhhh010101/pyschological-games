import unittest

from sqlalchemy import func, select

from backend.application.room_service import RoomService
from backend.application.session_service import SessionService
from backend.domain.exceptions import InvalidGameAction, UnauthorizedPlayer
from backend.infrastructure.database.models import (
    GameEventRecord,
    GameStateSnapshotRecord,
    PlayerRecord,
    ResultRecord,
)
from backend.infrastructure.database.repositories.sqlalchemy_room_repository import SQLAlchemyRoomRepository
from backend.infrastructure.database.session import create_database
from backend.settings import Settings


class PersistenceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        settings = Settings(
            app_env="test",
            database_url="sqlite+aiosqlite:///:memory:",
            room_idle_ttl_seconds=60,
            session_ttl_seconds=300,
        )
        self.engine, self.sessions = create_database(settings)
        self.repository = SQLAlchemyRoomRepository(
            self.engine,
            self.sessions,
            settings.room_idle_ttl_seconds,
        )
        await self.repository.initialize()
        self.service = RoomService(self.repository, SessionService(settings.session_ttl_seconds))

    async def asyncTearDown(self) -> None:
        await self.repository.close()

    async def test_room_state_sessions_results_and_events_are_durable(self) -> None:
        created = await self.service.create_room("Host", "vault")
        joined = await self.service.join_room(created["code"], "Guest")
        await self.service.start(created["code"], created["playerId"], "start-1")
        result = await self.service.force_resolve(created["code"], created["playerId"], "resolve-1")

        self.assertEqual(result["phase"], "results")
        guest_state = await self.service.public_state(created["code"], joined["playerId"])
        self.assertEqual(guest_state["viewerId"], result["players"][1]["id"])

        async with self.sessions() as session:
            event_count = await session.scalar(select(func.count()).select_from(GameEventRecord))
            snapshot_count = await session.scalar(select(func.count()).select_from(GameStateSnapshotRecord))
            result_count = await session.scalar(select(func.count()).select_from(ResultRecord))
            players = list(await session.scalars(select(PlayerRecord)))

        self.assertGreaterEqual(int(event_count or 0), 4)
        self.assertGreaterEqual(int(snapshot_count or 0), 4)
        self.assertEqual(result_count, 1)
        self.assertEqual(len(players), 2)
        self.assertNotIn(created["playerId"], {player.token_hash for player in players})

    async def test_idempotent_command_returns_the_original_response(self) -> None:
        created = await self.service.create_room("Host", "vault")
        await self.service.join_room(created["code"], "Guest")

        first = await self.service.start(created["code"], created["playerId"], "same-key")
        repeated = await self.service.start(created["code"], created["playerId"], "same-key")

        self.assertEqual(repeated, first)
        async with self.sessions() as session:
            snapshots = await session.scalar(select(func.count()).select_from(GameStateSnapshotRecord))
        self.assertEqual(snapshots, 3)

    async def test_invalid_join_rolls_back_and_invalid_token_is_rejected(self) -> None:
        created = await self.service.create_room("Host", "vault")
        await self.service.join_room(created["code"], "Guest")
        with self.assertRaises(InvalidGameAction):
            await self.service.join_room(created["code"], "guest")
        with self.assertRaises(UnauthorizedPlayer):
            await self.service.public_state(created["code"], "not-a-session")

        async with self.sessions() as session:
            player_count = await session.scalar(select(func.count()).select_from(PlayerRecord))
        self.assertEqual(player_count, 2)


if __name__ == "__main__":
    unittest.main()
