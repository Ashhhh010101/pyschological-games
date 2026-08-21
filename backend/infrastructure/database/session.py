"""Database engine and session factory construction."""

from pathlib import Path
from typing import Any

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.settings import Settings


def create_database(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    database_url = make_url(settings.database_url)
    if settings.database_backend == "sqlite":
        database_path = database_url.database
        if database_path and database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {"echo": settings.database_echo, "pool_pre_ping": True}
    if settings.database_backend == "postgresql":
        options["pool_size"] = settings.database_pool_size
    engine = create_async_engine(settings.database_url, **options)
    if settings.database_backend == "sqlite":
        _configure_sqlite(engine, settings)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


def _configure_sqlite(engine: AsyncEngine, settings: Settings) -> None:
    @event.listens_for(engine.sync_engine, "connect")
    def set_sqlite_pragmas(dbapi_connection: Any, _connection_record: Any) -> None:
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute(f"PRAGMA busy_timeout={settings.sqlite_busy_timeout_ms}")
            if settings.sqlite_wal_enabled and make_url(settings.database_url).database != ":memory:":
                cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
        finally:
            cursor.close()
