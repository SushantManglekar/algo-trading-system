"""Application-scoped WebSocket topic fan-out for live market and signal updates."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from typing import Final

from fastapi import WebSocket

LIVE_TOPICS: Final[frozenset[str]] = frozenset({"ticks", "candles", "signals", "analytics"})


class LiveEventHub:
    """Broadcasts JSON events to subscribers without any module-level connection state."""

    def __init__(self) -> None:
        self._connections: dict[str, set[WebSocket]] = {topic: set() for topic in LIVE_TOPICS}
        self._lock = asyncio.Lock()

    async def subscribe(self, topic: str, websocket: WebSocket) -> None:
        """Accept a client and register it under a validated topic."""
        if topic not in LIVE_TOPICS:
            raise ValueError(f"unsupported live topic: {topic}")
        await websocket.accept()
        async with self._lock:
            self._connections[topic].add(websocket)

    async def unsubscribe(self, topic: str, websocket: WebSocket) -> None:
        """Remove a disconnected client without affecting other subscribers."""
        async with self._lock:
            self._connections.get(topic, set()).discard(websocket)

    async def publish(self, topic: str, event: str, payload: Mapping[str, object]) -> None:
        """Send one event to all current subscribers, pruning stale connections."""
        if topic not in LIVE_TOPICS:
            raise ValueError(f"unsupported live topic: {topic}")
        async with self._lock:
            connections = tuple(self._connections[topic])
        stale_connections: list[WebSocket] = []
        message = {"event": event, "data": payload}
        for websocket in connections:
            try:
                await websocket.send_json(message)
            except RuntimeError:
                stale_connections.append(websocket)
        for websocket in stale_connections:
            await self.unsubscribe(topic, websocket)
