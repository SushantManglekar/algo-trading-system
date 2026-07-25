"""Candle persistence boundary with a bounded in-memory implementation for the API."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from datetime import datetime

from market_data.types import Candle, CandleInterval


class InMemoryCandleStore:
    """Upserts active and completed candles while retaining bounded series history."""

    def __init__(self, max_candles_per_series: int) -> None:
        if max_candles_per_series <= 0:
            raise ValueError("max_candles_per_series must be positive")
        self._max_candles_per_series = max_candles_per_series
        self._candles: dict[tuple[str, CandleInterval], dict[datetime, Candle]] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, candle: Candle) -> None:
        async with self._lock:
            series = self._candles.setdefault((candle.symbol, candle.interval), {})
            series[candle.start_at] = candle
            while len(series) > self._max_candles_per_series:
                del series[min(series)]

    async def latest(self, symbol: str, interval: CandleInterval) -> Candle | None:
        async with self._lock:
            series = self._candles.get((symbol.upper(), interval), {})
            return series[max(series)] if series else None

    async def list_candles(
        self,
        symbol: str,
        interval: CandleInterval,
        start_at: datetime,
        end_at: datetime,
    ) -> Sequence[Candle]:
        async with self._lock:
            series = self._candles.get((symbol.upper(), interval), {})
            return tuple(
                series[start]
                for start in sorted(series)
                if start_at <= start and series[start].end_at <= end_at
            )
