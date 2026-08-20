"""WebSocket connection tracking isolated from HTTP route definitions."""

import inspect
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import WebSocket

from backend.domain.exceptions import ApplicationError


class ConnectionManager:
    """Track viewer-aware room sockets on the application's event loop."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[tuple[WebSocket, str]]] = {}

    async def connect(self, websocket: WebSocket, code: str, player_id: str) -> None:
        await websocket.accept()
        self._rooms.setdefault(code, set()).add((websocket, player_id))

    def disconnect(self, websocket: WebSocket, code: str, player_id: str) -> None:
        connections = self._rooms.get(code)
        if connections is None:
            return
        connections.discard((websocket, player_id))
        if not connections:
            self._rooms.pop(code, None)

    async def broadcast(
        self,
        code: str,
        state_for: Callable[[str], dict[str, Any] | Awaitable[dict[str, Any]]],
    ) -> None:
        """Send each player their own privacy-filtered room projection."""
        for websocket, player_id in self._rooms.get(code, set()).copy():
            try:
                state = state_for(player_id)
                await websocket.send_json(await state if inspect.isawaitable(state) else state)
            except (ApplicationError, RuntimeError, OSError):
                self.disconnect(websocket, code, player_id)

    async def close_room(self, code: str, reason: str = "Room expired") -> None:
        for websocket, player_id in self._rooms.get(code, set()).copy():
            try:
                await websocket.close(code=4001, reason=reason)
            finally:
                self.disconnect(websocket, code, player_id)

    async def close_all(self) -> None:
        for code in list(self._rooms):
            await self.close_room(code, "Server shutting down")
