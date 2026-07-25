"""Provider boundary for real-time and historical US equities market data."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator, Sequence

from market_data.types import Candle, HistoricalCandleRequest, MarketTick


class MarketDataProvider(ABC):
    """A provider adapter with explicit connection and subscription lifecycle management."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return a stable, configuration-facing provider identifier."""

    @abstractmethod
    async def connect(self) -> None:
        """Create authenticated upstream connections and allocate resources."""

    @abstractmethod
    async def disconnect(self) -> None:
        """Release all upstream connections and local resources."""

    @abstractmethod
    async def subscribe(self, symbols: Sequence[str]) -> None:
        """Subscribe to normalized real-time ticks for the supplied symbols."""

    @abstractmethod
    async def unsubscribe(self, symbols: Sequence[str]) -> None:
        """Stop receiving real-time ticks for the supplied symbols."""

    @abstractmethod
    async def get_historical_candles(
        self, request: HistoricalCandleRequest
    ) -> Sequence[Candle]:
        """Return candles in ascending start-time order for a bounded request."""

    @abstractmethod
    async def stream_ticks(self) -> AsyncIterator[MarketTick]:
        """Yield normalized ticks from the current subscriptions until disconnected."""
