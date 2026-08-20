"""FastAPI transport and lifecycle composition root."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import hashlib
import logging
import os
import re
import time
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from uuid import uuid4

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from sqlalchemy.ext.asyncio import AsyncEngine

from backend import __version__
from backend.api_models import ActionRequest, CreateRoomRequest, JoinRoomRequest, PlayerRequest
from backend.application.legacy_room_service import LegacyRoomService
from backend.application.ports import RoomApplication
from backend.application.room_service import RoomService
from backend.application.session_service import SessionService
from backend.config import GAME_CONFIG
from backend.connections import ConnectionManager
from backend.domain.exceptions import (
    ApplicationError,
    ConcurrentMutation,
    InvalidGameAction,
    PersistenceError,
    PlayerNotFound,
    RateLimitExceeded,
    RoomExpired,
    RoomNotFound,
    UnauthorizedPlayer,
)
from backend.domain.repositories import Cache, EventBus, RateLimiter
from backend.game import GameError, GameStore
from backend.infrastructure.database.repositories.sqlalchemy_room_repository import SQLAlchemyRoomRepository
from backend.infrastructure.database.session import create_database
from backend.infrastructure.http import PayloadSizeLimitMiddleware
from backend.infrastructure.observability.logging import bind_context, configure_logging
from backend.infrastructure.observability.telemetry import configure_telemetry
from backend.infrastructure.redis.cache import MemoryCache, RedisCache
from backend.infrastructure.redis.pubsub import LocalEventBus, RedisEventBus
from backend.infrastructure.redis.rate_limit import MemoryRateLimiter, RedisRateLimiter
from backend.settings import Settings, get_settings

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
LOGGER = logging.getLogger("psychological_games.api")
REQUEST_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")

ERROR_STATUSES: dict[type[ApplicationError], int] = {
    RoomNotFound: 404,
    PlayerNotFound: 404,
    UnauthorizedPlayer: 401,
    InvalidGameAction: 409,
    ConcurrentMutation: 409,
    RoomExpired: 410,
    RateLimitExceeded: 429,
    PersistenceError: 503,
}


def _error(code: str, message: str) -> dict[str, dict[str, str]]:
    return {"error": {"code": code, "message": message}}


def _token_identity(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_app(store: GameStore | None = None, runtime_settings: Settings | None = None) -> FastAPI:
    """Build an isolated app; production defaults to SQL plus optional Redis."""
    settings = runtime_settings or get_settings()
    if store is None:
        configure_logging(settings.log_level, settings.log_json)
    connections = ConnectionManager()
    repository: SQLAlchemyRoomRepository | None = None
    database_engine: AsyncEngine | None = None

    if settings.redis_url:
        cache: Cache = RedisCache(settings.redis_url, settings.redis_key_prefix)
        event_bus: EventBus = RedisEventBus(settings.redis_url, settings.redis_key_prefix)
        limiter: RateLimiter = RedisRateLimiter(
            settings.redis_url,
            settings.redis_key_prefix,
            settings.rate_limit_enabled,
        )
    else:
        cache = MemoryCache()
        event_bus = LocalEventBus()
        limiter = MemoryRateLimiter(settings.rate_limit_enabled)

    if store is not None:
        service: RoomApplication = LegacyRoomService(store)
    else:
        database_engine, sessions = create_database(settings)
        repository = SQLAlchemyRoomRepository(
            database_engine,
            sessions,
            settings.room_idle_ttl_seconds,
            auto_create=settings.app_env != "production",
        )
        service = RoomService(
            repository,
            SessionService(settings.session_ttl_seconds),
            event_bus,
            cache,
            settings.room_idle_ttl_seconds,
        )

    async def fan_out(code: str, version: int) -> None:
        normalized = code.upper()
        if version < 0:
            await connections.close_room(normalized)
            return
        await connections.broadcast(normalized, lambda token: service.public_state(normalized, token))

    async def expiry_worker() -> None:
        while True:
            await asyncio.sleep(settings.expiry_scan_interval_seconds)
            await service.expire_idle_rooms()

    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        if repository is not None:
            await repository.initialize()
        await event_bus.start(fan_out)
        expiry_task = asyncio.create_task(expiry_worker(), name="room-expiry")
        try:
            yield
        finally:
            expiry_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await expiry_task
            await connections.close_all()
            await event_bus.close()
            await limiter.close()
            await cache.close()
            if repository is not None:
                await repository.close()
            observability.shutdown()

    app = FastAPI(
        title="Psychological Games API",
        version=__version__,
        description="Server-authoritative multiplayer API for five loss-aversion games.",
        lifespan=lifespan,
    )
    observability = configure_telemetry(app, settings, database_engine)
    app.state.room_service = service
    app.state.repository = repository
    app.state.cache = cache
    app.state.event_bus = event_bus
    app.state.rate_limiter = limiter
    app.state.connections = connections
    if store is not None:
        app.state.game_store = store

    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.hosts or ["*"])
    if settings.origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.origins,
            allow_credentials=False,
            allow_methods=["GET", "POST"],
            allow_headers=["Content-Type", "X-Request-ID"],
        )
    app.add_middleware(PayloadSizeLimitMiddleware, max_bytes=settings.payload_max_bytes)

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        candidate = request.headers.get("x-request-id", "")
        request_id = candidate if REQUEST_ID.fullmatch(candidate) else str(uuid4())
        parts = request.url.path.split("/")
        room_code = parts[3].upper() if len(parts) > 3 and parts[1:3] == ["api", "rooms"] else ""
        binding = bind_context(request_id, room_code, f"{request.method} {request.url.path}")
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (time.perf_counter() - started) * 1000
            observability.record_request(request.method, request.url.path, 500, duration_ms)
            LOGGER.exception(
                "Unhandled request failure",
                extra={
                    "event": "http.request.failed",
                    "http_method": request.method,
                    "http_path": request.url.path,
                    "http_status": 500,
                    "duration_ms": round(duration_ms, 3),
                },
            )
            binding.reset()
            raise
        duration_ms = (time.perf_counter() - started) * 1000
        observability.record_request(request.method, request.url.path, response.status_code, duration_ms)
        LOGGER.info(
            "Request completed",
            extra={
                "event": "http.request.completed",
                "http_method": request.method,
                "http_path": request.url.path,
                "http_status": response.status_code,
                "duration_ms": round(duration_ms, 3),
            },
        )
        response.headers["X-Request-ID"] = request_id
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self' ws: wss:; img-src 'self' data:; "
            "script-src 'self' https://cdn.jsdelivr.net; "
            "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
            "base-uri 'self'; form-action 'self'; frame-ancestors 'none'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        binding.reset()
        return response

    def client_identity(request: Request) -> str:
        if settings.trust_proxy_headers:
            forwarded = request.headers.get("x-forwarded-for", "").split(",", maxsplit=1)[0].strip()
            if forwarded:
                return forwarded
        return request.client.host if request.client else "unknown"

    @app.exception_handler(ApplicationError)
    async def application_error_handler(_request: Request, exc: ApplicationError) -> JSONResponse:
        return JSONResponse(status_code=ERROR_STATUSES.get(type(exc), 400), content=_error(exc.code, str(exc)))

    @app.exception_handler(GameError)
    async def game_error_handler(_request: Request, exc: GameError) -> JSONResponse:
        code = type(exc).__name__.replace("Error", "").upper()
        return JSONResponse(status_code=exc.status_code, content=_error(code, str(exc)))

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", [])[1:]) or "request"
        message = str(first.get("msg", "Invalid request"))
        return JSONResponse(status_code=422, content=_error("VALIDATION_ERROR", f"{location}: {message}"))

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_request: Request, _exc: Exception) -> JSONResponse:
        return JSONResponse(
            status_code=500,
            content=_error("INTERNAL_SERVER_ERROR", "An unexpected server error occurred."),
        )

    @app.get("/api/health")
    async def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "games": list(GAME_CONFIG)}

    @app.get("/api/ready")
    async def ready() -> JSONResponse:
        database_ready = repository is None or await repository.ready()
        dependencies = {
            "database": database_ready,
            "cache": await cache.ready(),
            "eventBus": await event_bus.ready(),
        }
        healthy = all(dependencies.values())
        return JSONResponse(
            status_code=200 if healthy else 503,
            content={"status": "ready" if healthy else "not-ready", "dependencies": dependencies},
        )

    @app.get("/api/games")
    async def games() -> list[dict[str, Any]]:
        return [
            {"id": game_id, "name": config["name"], "rounds": config["rounds"]}
            for game_id, config in GAME_CONFIG.items()
        ]

    @app.post("/api/rooms", status_code=201)
    async def create_room(request: Request, payload: CreateRoomRequest) -> dict[str, str]:
        await limiter.check("room-create", client_identity(request), settings.room_create_limit)
        return await service.create_room(payload.name, payload.game_id)

    @app.post("/api/rooms/{code}/join", status_code=201)
    async def join_room(code: str, request: Request, payload: JoinRoomRequest) -> dict[str, str]:
        await limiter.check("room-join", client_identity(request), settings.room_join_limit)
        return await service.join_room(code, payload.name)

    @app.get("/api/rooms/{code}")
    async def get_room(code: str, playerId: str) -> dict[str, Any]:
        return await service.public_state(code, playerId)

    @app.websocket("/api/rooms/{code}/ws")
    async def room_socket(websocket: WebSocket, code: str, playerId: str) -> None:
        normalized = code.upper()
        identity = websocket.client.host if websocket.client else "unknown"
        try:
            await limiter.check("websocket", identity, settings.websocket_limit)
            initial_state = await service.public_state(normalized, playerId)
        except (ApplicationError, GameError) as exc:
            await websocket.close(code=1008, reason=str(exc))
            return
        await connections.connect(websocket, normalized, playerId)
        try:
            await websocket.send_json(initial_state)
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        finally:
            connections.disconnect(websocket, normalized, playerId)

    @app.post("/api/rooms/{code}/start")
    async def start_room(code: str, payload: PlayerRequest) -> dict[str, Any]:
        await limiter.check("action", _token_identity(payload.player_id), settings.action_limit)
        return await service.start(code, payload.player_id, payload.idempotency_key)

    @app.post("/api/rooms/{code}/actions")
    async def submit_action(code: str, payload: ActionRequest) -> dict[str, Any]:
        await limiter.check("action", _token_identity(payload.player_id), settings.action_limit)
        return await service.submit_action(code, payload.player_id, payload.values, payload.idempotency_key)

    @app.post("/api/rooms/{code}/resolve")
    async def resolve_room(code: str, payload: PlayerRequest) -> dict[str, Any]:
        await limiter.check("resolve", _token_identity(payload.player_id), settings.resolve_limit)
        return await service.force_resolve(code, payload.player_id, payload.idempotency_key)

    @app.post("/api/rooms/{code}/next")
    async def next_round(code: str, payload: PlayerRequest) -> dict[str, Any]:
        await limiter.check("action", _token_identity(payload.player_id), settings.action_limit)
        return await service.next_round(code, payload.player_id, payload.idempotency_key)

    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
    return app


app = create_app()


def valid_port(value: str) -> int:
    """Parse and range-check a TCP port for CLI and environment defaults."""
    try:
        port = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("port must be a whole number") from exc
    if not 1 <= port <= 65535:
        raise argparse.ArgumentTypeError("port must be between 1 and 65535")
    return port


def main() -> None:
    """Run the application with CLI flags overriding environment defaults."""
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Run the Psychological Games FastAPI server")
    parser.add_argument("--host", default=os.getenv("HOST", settings.host))
    parser.add_argument("--port", default=os.getenv("PORT", str(settings.port)), type=valid_port)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, proxy_headers=settings.trust_proxy_headers)


if __name__ == "__main__":
    main()
