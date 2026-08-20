"""WebSocket connection tracking isolated from HTTP route definitions."""

from collections.abc import Callable
from typing import Any

from fastapi import WebSocket


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

    async def broadcast(self, code: str, state_for: Callable[[str], dict[str, Any]]) -> None:
        """Send each player their own privacy-filtered room projection."""
        for websocket, player_id in self._rooms.get(code, set()).copy():
            try:
                await websocket.send_json(state_for(player_id))
            except RuntimeError:
                self.disconnect(websocket, code, player_id)
