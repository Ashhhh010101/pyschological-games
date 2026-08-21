"""Wait for the configured database and apply Alembic migrations."""

from __future__ import annotations

import asyncio
import logging

from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from alembic import command
from backend.infrastructure.database.session import create_database
from backend.infrastructure.observability.logging import configure_logging
from backend.settings import Settings, get_settings

LOGGER = logging.getLogger("psychological_games.migrate")


async def wait_for_database(settings: Settings) -> None:
    engine, _ = create_database(settings)
    try:
        for attempt in range(1, settings.database_connect_attempts + 1):
            try:
                async with engine.connect() as connection:
                    await connection.execute(text("SELECT 1"))
                return
            except SQLAlchemyError:
                if attempt == settings.database_connect_attempts:
                    raise
                LOGGER.warning(
                    "Database is not ready",
                    extra={"event": "database.waiting", "attempt": attempt},
                )
                await asyncio.sleep(settings.database_retry_delay_seconds)
    finally:
        await engine.dispose()


def main() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_json)
    asyncio.run(wait_for_database(settings))
    command.upgrade(Config("alembic.ini"), "head")
    LOGGER.info(
        "Database migration complete",
        extra={"event": "database.migrated", "database_backend": settings.database_backend},
    )


if __name__ == "__main__":
    main()
