from __future__ import annotations

from pathlib import Path
from typing import Any, Literal
import argparse

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field

from backend.game import GAME_CONFIG, GameError, GameStore


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
GameId = Literal["vault", "burden", "chain", "insurance", "reputation"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateRoomRequest(StrictModel):
    name: str = Field(min_length=1, max_length=24)
    gameId: GameId


class JoinRoomRequest(StrictModel):
    name: str = Field(min_length=1, max_length=24)


class PlayerRequest(StrictModel):
    playerId: str = Field(min_length=1, max_length=128)


class ActionRequest(PlayerRequest):
    idempotencyKey: str = Field(min_length=1, max_length=128)
    values: dict[str, Any]


def create_app(store: GameStore | None = None) -> FastAPI:
    game_store = store or GameStore()
    app = FastAPI(
        title="Psychological Games API",
        version="2.0.0",
        description="Server-authoritative local multiplayer API for five loss-aversion games.",
    )
    app.state.game_store = game_store

    @app.exception_handler(GameError)
    async def game_error_handler(_request: Request, exc: GameError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"error": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
        first = exc.errors()[0] if exc.errors() else {}
        location = ".".join(str(part) for part in first.get("loc", [])[1:]) or "request"
        message = first.get("msg", "Invalid request")
        return JSONResponse(status_code=422, content={"error": f"{location}: {message}"})

    @app.get("/api/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "games": list(GAME_CONFIG), "rooms": len(game_store.rooms)}

    @app.get("/api/games")
    def games() -> list[dict[str, Any]]:
        return [
            {"id": game_id, "name": config["name"], "rounds": config["rounds"]}
            for game_id, config in GAME_CONFIG.items()
        ]

    @app.post("/api/rooms", status_code=201)
    def create_room(payload: CreateRoomRequest) -> dict[str, str]:
        room, player = game_store.create_room(payload.name, payload.gameId)
        return {"code": room.code, "playerId": player.id}

    @app.post("/api/rooms/{code}/join", status_code=201)
    def join_room(code: str, payload: JoinRoomRequest) -> dict[str, str]:
        room, player = game_store.join_room(code, payload.name)
        return {"code": room.code, "playerId": player.id}

    @app.get("/api/rooms/{code}")
    def get_room(code: str, playerId: str) -> dict[str, Any]:
        return game_store.public_state(code, playerId)

    @app.post("/api/rooms/{code}/start")
    def start_room(code: str, payload: PlayerRequest) -> dict[str, Any]:
        game_store.start(code, payload.playerId)
        return game_store.public_state(code, payload.playerId)

    @app.post("/api/rooms/{code}/actions")
    def submit_action(code: str, payload: ActionRequest) -> dict[str, Any]:
        game_store.submit_action(code, payload.playerId, payload.values, payload.idempotencyKey)
        return game_store.public_state(code, payload.playerId)

    @app.post("/api/rooms/{code}/resolve")
    def resolve_room(code: str, payload: PlayerRequest) -> dict[str, Any]:
        game_store.force_resolve(code, payload.playerId)
        return game_store.public_state(code, payload.playerId)

    @app.post("/api/rooms/{code}/next")
    def next_round(code: str, payload: PlayerRequest) -> dict[str, Any]:
        game_store.next_round(code, payload.playerId)
        return game_store.public_state(code, payload.playerId)

    # API routes must be registered before the root static mount.
    app.mount("/", StaticFiles(directory=FRONTEND, html=True), name="frontend")
    return app


app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Psychological Games FastAPI server")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=8000, type=int)
    args = parser.parse_args()
    print(f"Psychological Games: http://{args.host}:{args.port}")
    print(f"Interactive API docs: http://{args.host}:{args.port}/docs")
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
