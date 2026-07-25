"""Validation, chronological ordering, and persistence of incoming market ticks."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from typing import Any

from market_data.provider import MarketDataProvider
from market_data.tick_store import TickStore
from market_data.types import MarketTick


class TickProcessingStatus(StrEnum):
    """Terminal outcome for an incoming tick."""

    ACCEPTED = "accepted"
    DROPPED_OUT_OF_ORDER = "dropped_out_of_order"


@dataclass(frozen=True, slots=True)
class TickProcessorSettings:
    """Risk-sensitive processing policy, supplied through application configuration."""

    reject_out_of_order_ticks: bool = True


@dataclass(frozen=True, slots=True)
class TickProcessingResult:
    """Audit-friendly processing outcome for one validated tick."""

    tick: MarketTick
    status: TickProcessingStatus
    reason: str | None = None

    @property
    def accepted(self) -> bool:
        return self.status is TickProcessingStatus.ACCEPTED


class TickProcessor:
    """Processes only timestamp-monotonic ticks before exposing them downstream.

    A timestamp older than the accepted symbol watermark is dropped by default. This
    conservative policy prevents late packets from mutating the state seen by candles
    and strategies; a future reorder-buffer implementation can be configured explicitly.
    """

    def __init__(self, store: TickStore, settings: TickProcessorSettings) -> None:
        self._store = store
        self._settings = settings
        self._latest_timestamp_by_symbol: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def process(self, payload: MarketTick | Mapping[str, Any]) -> TickProcessingResult:
        """Normalize, validate, order-check, and persist one tick."""
        tick = payload if isinstance(payload, MarketTick) else MarketTick.model_validate(payload)

        async with self._lock:
            latest_timestamp = self._latest_timestamp_by_symbol.get(tick.symbol)
            if (
                self._settings.reject_out_of_order_ticks
                and latest_timestamp is not None
                and tick.timestamp < latest_timestamp
            ):
                return TickProcessingResult(
                    tick=tick,
                    status=TickProcessingStatus.DROPPED_OUT_OF_ORDER,
                    reason="timestamp_precedes_symbol_watermark",
                )

            await self._store.append(tick)
            if latest_timestamp is None or tick.timestamp > latest_timestamp:
                self._latest_timestamp_by_symbol[tick.symbol] = tick.timestamp
            return TickProcessingResult(tick=tick, status=TickProcessingStatus.ACCEPTED)

    async def consume(self, provider: MarketDataProvider) -> AsyncIterator[TickProcessingResult]:
        """Process every tick emitted by a connected provider stream."""
        async for tick in provider.stream_ticks():
            yield await self.process(tick)
