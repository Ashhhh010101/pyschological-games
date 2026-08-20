from __future__ import annotations

import argparse
import os
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from backend import __version__
from backend.api_models import (
    ActionRequest,
    CreateRoomRequest,
    JoinRoomRequest,
    PlayerRequest,
)
from backend.config import GAME_CONFIG
from backend.connections import ConnectionManager
from backend.game import GameError, GameStore

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"


def create_app(store: GameStore | None = None) -> FastAPI:
    """Build an isolated application instance for production or tests."""
    game_store = store or GameStore()
    connections = ConnectionManager()
    app = FastAPI(
        title="Psychological Games API",
        version=__version__,
        description="Server-authoritative local multiplayer API for five loss-aversion games.",
    )
    app.state.game_store = game_store
    app.state.connections = connections

    @app.middleware("http")
    async def security_headers(
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        response = await call_next(request)
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; "
            "connect-src 'self' ws: wss:; "
            "img-src 'self' data:; "
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
        return response

    async def broadcast(code: str) -> None:
        normalized = code.upper()
        await connections.broadcast(normalized, lambda player_id: game_store.public_state(normalized, player_id))

    @app.exception_handler(GameError)
    async def game_error_handler(_request: Request, exc: GameError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"error": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", [])[1:]) or "request"
        message = first.get("msg", "Invalid request")
        return JSONResponse(status_code=422, content={"error": f"{location}: {message}"})

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "version": __version__, "games": list(GAME_CONFIG), "rooms": game_store.room_count}

    @app.get("/api/games")
    def games() -> list[dict[str, Any]]:
        return [
            {"id": game_id, "name": config["name"], "rounds": config["rounds"]}
            for game_id, config in GAME_CONFIG.items()
        ]

    @app.post("/api/rooms", status_code=201)
    def create_room(payload: CreateRoomRequest) -> dict[str, str]:
        room, player = game_store.create_room(payload.name, payload.game_id)
        return {"code": room.code, "playerId": player.id}

    @app.post("/api/rooms/{code}/join", status_code=201)
    def join_room(code: str, payload: JoinRoomRequest) -> dict[str, str]:
        room, player = game_store.join_room(code, payload.name)
        return {"code": room.code, "playerId": player.id}

    @app.get("/api/rooms/{code}")
    def get_room(code: str, playerId: str) -> dict[str, Any]:
        return game_store.public_state(code, playerId)

    @app.websocket("/api/rooms/{code}/ws")
    async def room_socket(websocket: WebSocket, code: str, playerId: str) -> None:
        normalized = code.upper()
        try:
            initial_state = game_store.public_state(normalized, playerId)
        except GameError as exc:
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
        game_store.start(code, payload.player_id)
        await broadcast(code)
        return game_store.public_state(code, payload.player_id)

    @app.post("/api/rooms/{code}/actions")
    async def submit_action(code: str, payload: ActionRequest) -> dict[str, Any]:
        game_store.submit_action(code, payload.player_id, payload.values, payload.idempotency_key)
        await broadcast(code)
        return game_store.public_state(code, payload.player_id)

    @app.post("/api/rooms/{code}/resolve")
    async def resolve_room(code: str, payload: PlayerRequest) -> dict[str, Any]:
        game_store.force_resolve(code, payload.player_id)
        await broadcast(code)
        return game_store.public_state(code, payload.player_id)

    @app.post("/api/rooms/{code}/next")
    async def next_round(code: str, payload: PlayerRequest) -> dict[str, Any]:
        game_store.next_round(code, payload.player_id)
        await broadcast(code)
        return game_store.public_state(code, payload.player_id)

    # API routes must be registered before the root static mount.
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
    parser = argparse.ArgumentParser(description="Run the Psychological Games FastAPI server")
    parser.add_argument("--host", default=os.getenv("HOST", "127.0.0.1"))
    parser.add_argument("--port", default=os.getenv("PORT", "8000"), type=valid_port)
    args = parser.parse_args()
    print(f"Psychological Games: http://{args.host}:{args.port}")
    print(f"Interactive API docs: http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
