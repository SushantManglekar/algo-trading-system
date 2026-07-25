"""Deterministic in-memory provider for development, tests, and replay workflows."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Iterable, Sequence
from dataclasses import dataclass
from typing import Final

from market_data.provider import MarketDataProvider
from market_data.types import Candle, HistoricalCandleRequest, MarketTick
from providers.exceptions import ProviderNotConnectedError

_STREAM_STOP: Final = object()


@dataclass(frozen=True, slots=True)
class MockProviderSettings:
    """Configuration for a deterministic, in-process provider adapter."""

    name: str = "mock"


class MockMarketDataProvider(MarketDataProvider):
    """Replay-safe provider that emits only explicitly injected, subscribed ticks.

    It is intentionally useful beyond unit tests: workers can use it for deterministic
    historical replays and local development without broker or vendor credentials.
    """

    def __init__(
        self,
        settings: MockProviderSettings | None = None,
        historical_candles: Iterable[Candle] = (),
    ) -> None:
        self._settings = settings or MockProviderSettings()
        if not self._settings.name.strip():
            raise ValueError("mock provider name cannot be blank")

        self._historical_candles = tuple(
            sorted(
                historical_candles,
                key=lambda candle: (candle.symbol, candle.interval, candle.start_at),
            )
        )
        self._connected = False
        self._subscriptions: set[str] = set()
        self._queue: asyncio.Queue[MarketTick | object] = asyncio.Queue()
        self._state_lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return self._settings.name

    @property
    def is_connected(self) -> bool:
        """Expose current lifecycle state for health checks and integration tests."""
        return self._connected

    @property
    def subscriptions(self) -> frozenset[str]:
        """Return an immutable snapshot of active symbol subscriptions."""
        return frozenset(self._subscriptions)

    async def connect(self) -> None:
        async with self._state_lock:
            if self._connected:
                return
            self._queue = asyncio.Queue()
            self._connected = True

    async def disconnect(self) -> None:
        async with self._state_lock:
            if not self._connected:
                return
            self._connected = False
            self._subscriptions.clear()
            await self._queue.put(_STREAM_STOP)

    async def subscribe(self, symbols: Sequence[str]) -> None:
        normalized_symbols = self._normalize_symbols(symbols)
        async with self._state_lock:
            self._require_connection()
            self._subscriptions.update(normalized_symbols)

    async def unsubscribe(self, symbols: Sequence[str]) -> None:
        normalized_symbols = self._normalize_symbols(symbols)
        async with self._state_lock:
            self._require_connection()
            self._subscriptions.difference_update(normalized_symbols)

    async def get_historical_candles(
        self, request: HistoricalCandleRequest
    ) -> Sequence[Candle]:
        async with self._state_lock:
            self._require_connection()
            return tuple(
                candle
                for candle in self._historical_candles
                if candle.symbol == request.symbol
                and candle.interval == request.interval
                and candle.is_complete
                and candle.start_at >= request.start_at
                and candle.end_at <= request.end_at
            )

    async def stream_ticks(self) -> AsyncIterator[MarketTick]:
        """Yield injected ticks until disconnect; a single provider has one upstream feed."""
        async with self._state_lock:
            self._require_connection()
            queue = self._queue

        while True:
            item = await queue.get()
            if item is _STREAM_STOP:
                return
            if isinstance(item, MarketTick):
                yield item

    async def publish_tick(self, tick: MarketTick) -> bool:
        """Inject one normalized tick, returning whether a subscriber received it.

        The method deliberately refuses unconnected or unsubscribed delivery, making
        test replays obey the same subscription contract as a live provider.
        """
        async with self._state_lock:
            self._require_connection()
            if tick.symbol not in self._subscriptions:
                return False
            await self._queue.put(tick)
            return True

    def _require_connection(self) -> None:
        if not self._connected:
            raise ProviderNotConnectedError("provider is not connected")

    @staticmethod
    def _normalize_symbols(symbols: Sequence[str]) -> set[str]:
        normalized_symbols = {symbol.strip().upper() for symbol in symbols}
        if not normalized_symbols or "" in normalized_symbols:
            raise ValueError("at least one non-blank symbol is required")
        return normalized_symbols
