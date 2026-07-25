"""Tick persistence boundary and a bounded in-memory implementation."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Sequence
from datetime import datetime
from typing import Protocol

from market_data.types import MarketTick


class TickStore(Protocol):
    """Persistence operations required by the tick-processing service."""

    async def append(self, tick: MarketTick) -> None:
        """Persist an accepted, normalized tick."""

    async def latest(self, symbol: str) -> MarketTick | None:
        """Return the latest accepted tick for a symbol, if one exists."""

    async def list_ticks(
        self,
        symbol: str,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = None,
    ) -> Sequence[MarketTick]:
        """Return accepted ticks in ascending event-time order."""


class InMemoryTickStore:
    """Bounded development adapter; production storage is introduced in Step 9."""

    def __init__(self, max_ticks_per_symbol: int) -> None:
        if max_ticks_per_symbol <= 0:
            raise ValueError("max_ticks_per_symbol must be positive")
        self._max_ticks_per_symbol = max_ticks_per_symbol
        self._ticks_by_symbol: dict[str, deque[MarketTick]] = {}
        self._lock = asyncio.Lock()

    async def append(self, tick: MarketTick) -> None:
        async with self._lock:
            ticks = self._ticks_by_symbol.setdefault(
                tick.symbol, deque(maxlen=self._max_ticks_per_symbol)
            )
            ticks.append(tick)

    async def latest(self, symbol: str) -> MarketTick | None:
        async with self._lock:
            ticks = self._ticks_by_symbol.get(symbol.upper())
            return ticks[-1] if ticks else None

    async def list_ticks(
        self,
        symbol: str,
        *,
        start_at: datetime | None = None,
        end_at: datetime | None = None,
        limit: int | None = None,
    ) -> Sequence[MarketTick]:
        if limit is not None and limit <= 0:
            raise ValueError("limit must be positive when supplied")
        async with self._lock:
            ticks = tuple(self._ticks_by_symbol.get(symbol.upper(), ()))

        result = tuple(
            tick
            for tick in ticks
            if (start_at is None or tick.timestamp >= start_at)
            and (end_at is None or tick.timestamp <= end_at)
        )
        return result[-limit:] if limit is not None else result
