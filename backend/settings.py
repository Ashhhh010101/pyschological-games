"""Centralized, environment-driven application configuration."""

from functools import lru_cache
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Validated runtime settings loaded from environment variables or `.env`."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_env: Literal["development", "test", "production"] = "development"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    database_url: str = "sqlite+aiosqlite:///./data/psychological_games.db"
    database_echo: bool = False
    database_pool_size: int = Field(default=10, ge=1, le=100)
    database_connect_attempts: int = Field(default=30, ge=1, le=300)
    database_retry_delay_seconds: float = Field(default=1.0, ge=0.1, le=30)
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=100, le=120_000)
    sqlite_wal_enabled: bool = True
    redis_url: str | None = None
    redis_key_prefix: str = "psychological-games"
    room_idle_ttl_seconds: int = Field(default=3600, ge=60)
    expiry_scan_interval_seconds: int = Field(default=60, ge=5, le=3600)
    lock_timeout_seconds: int = Field(default=15, ge=5, le=120)
    lock_wait_seconds: int = Field(default=5, ge=1, le=60)
    session_ttl_seconds: int = Field(default=86400, ge=300)
    payload_max_bytes: int = Field(default=65536, ge=1024, le=10_485_760)
    rate_limit_enabled: bool = True
    room_create_limit: str = "10/minute"
    room_join_limit: str = "30/minute"
    action_limit: str = "60/minute"
    resolve_limit: str = "30/minute"
    websocket_limit: str = "30/minute"
    allowed_origins: str = ""
    trusted_hosts: str = "*"
    trust_proxy_headers: bool = False
    log_level: str = "INFO"
    log_json: bool = True
    otel_enabled: bool = False
    otel_service_name: str = "loss-aversion-arcade"
    otel_exporter_otlp_endpoint: str | None = None

    @field_validator("database_url")
    @classmethod
    def require_async_database_driver(cls, value: str) -> str:
        if not value.startswith(("sqlite+aiosqlite://", "postgresql+asyncpg://")):
            raise ValueError("DATABASE_URL must use sqlite+aiosqlite or postgresql+asyncpg")
        return value

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise ValueError("LOG_LEVEL is invalid")
        return normalized

    @property
    def origins(self) -> list[str]:
        return [origin.strip() for origin in self.allowed_origins.split(",") if origin.strip()]

    @property
    def hosts(self) -> list[str]:
        return [host.strip() for host in self.trusted_hosts.split(",") if host.strip()]

    @property
    def database_backend(self) -> Literal["sqlite", "postgresql"]:
        return "sqlite" if self.database_url.startswith("sqlite+aiosqlite://") else "postgresql"


@lru_cache
def get_settings() -> Settings:
    """Return one immutable-by-convention settings object per process."""
    return Settings()
