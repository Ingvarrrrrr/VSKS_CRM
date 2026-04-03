"""
In-memory WebSocket connection manager for chat.
Stores user_id -> list of active WebSocket connections (multi-tab support).
Single-instance Docker deployment — no Redis needed.
"""
from __future__ import annotations

import logging
from typing import Dict, List

from fastapi import WebSocket

logger = logging.getLogger(__name__)


class ConnectionManager:
    def __init__(self) -> None:
        # user_id -> list of active websocket connections (multi-tab support)
        self.active: Dict[int, List[WebSocket]] = {}

    async def connect(self, user_id: int, ws: WebSocket) -> None:
        await ws.accept()
        self.active.setdefault(user_id, []).append(ws)
        logger.debug("WS connected: user_id=%s, total_conns=%s", user_id, len(self.active.get(user_id, [])))

    def disconnect(self, user_id: int, ws: WebSocket) -> None:
        conns = self.active.get(user_id, [])
        if ws in conns:
            conns.remove(ws)
        if not conns:
            self.active.pop(user_id, None)
        logger.debug("WS disconnected: user_id=%s", user_id)

    async def send_to_user(self, user_id: int, data: dict) -> None:
        """Push JSON message to all connections of a user. Silent on offline/error."""
        dead: list[WebSocket] = []
        for ws in self.active.get(user_id, []):
            try:
                await ws.send_json(data)
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.disconnect(user_id, ws)

    async def send_to_users(self, user_ids: list[int], data: dict) -> None:
        """Push JSON message to all connections of multiple users."""
        for uid in user_ids:
            await self.send_to_user(uid, data)

    def is_online(self, user_id: int) -> bool:
        return bool(self.active.get(user_id))


# Module-level singleton — imported by routers/chat.py
manager = ConnectionManager()
