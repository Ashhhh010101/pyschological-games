"""Database engine and session factory construction."""

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from backend.settings import Settings


def create_database(settings: Settings) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    if settings.database_url.startswith("sqlite+aiosqlite:///"):
        database_path = settings.database_url.removeprefix("sqlite+aiosqlite:///")
        if database_path and database_path != ":memory:":
            Path(database_path).parent.mkdir(parents=True, exist_ok=True)
    options: dict[str, object] = {"echo": settings.database_echo, "pool_pre_ping": True}
    if settings.database_url.startswith("postgresql+asyncpg://"):
        options["pool_size"] = settings.database_pool_size
    engine = create_async_engine(settings.database_url, **options)
    return engine, async_sessionmaker(engine, expire_on_commit=False)
