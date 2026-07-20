from __future__ import annotations

import asyncio
import json
from collections import defaultdict
from typing import Any

from fastapi import WebSocket
from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.config import settings


class ConnectionManager:
    """Tracks sockets for the current API process."""

    def __init__(self) -> None:
        self._rooms: dict[str, set[WebSocket]] = defaultdict(set)

    async def connect(self, room_code: str, websocket: WebSocket) -> None:
        await websocket.accept()
        self._rooms[room_code].add(websocket)

    def disconnect(self, room_code: str, websocket: WebSocket) -> None:
        sockets = self._rooms.get(room_code)
        if sockets is None:
            return
        sockets.discard(websocket)
        if not sockets:
            self._rooms.pop(room_code, None)

    async def broadcast(self, room_code: str, payload: dict[str, Any]) -> None:
        sockets = list(self._rooms.get(room_code, ()))
        if not sockets:
            return
        results = await asyncio.gather(
            *(socket.send_json(payload) for socket in sockets),
            return_exceptions=True,
        )
        for socket, result in zip(sockets, results, strict=True):
            if isinstance(result, Exception):
                self.disconnect(room_code, socket)


class RedisRoomState:
    """Fast snapshot cache; PostgreSQL remains the durable source of truth."""

    def __init__(self) -> None:
        self.redis = Redis.from_url(settings.redis_url, decode_responses=True)

    async def save(self, room_code: str, payload: dict[str, Any]) -> None:
        try:
            await self.redis.set(
                f"watch-room:{room_code}",
                json.dumps(payload),
                ex=60 * 60 * 24,
            )
        except RedisError:
            # Local development can still run if Redis has not been started yet.
            return

    async def get(self, room_code: str) -> dict[str, Any] | None:
        try:
            raw = await self.redis.get(f"watch-room:{room_code}")
        except RedisError:
            return None
        return json.loads(raw) if raw else None

    async def close(self) -> None:
        await self.redis.aclose()


connections = ConnectionManager()
room_state_cache = RedisRoomState()

