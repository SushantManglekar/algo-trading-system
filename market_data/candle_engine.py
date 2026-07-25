"""Real-time, no-look-ahead aggregation of validated ticks into XNYS candles."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from market_data.exchange_calendar import CandleBucket, XnysExchangeCalendar
from market_data.types import Candle, CandleInterval, MarketTick


@dataclass(frozen=True, slots=True)
class CandleEngineSettings:
    """Candle intervals enabled by runtime configuration."""

    intervals: tuple[CandleInterval, ...]


@dataclass(frozen=True, slots=True)
class CandleUpdate:
    """All state transitions created while applying one tick or time watermark."""

    updated: tuple[Candle, ...] = ()
    completed: tuple[Candle, ...] = ()
    ignored: bool = False
    reason: str | None = None


@dataclass(slots=True)
class _ActiveCandle:
    symbol: str
    interval: CandleInterval
    bucket: CandleBucket
    open: Decimal
    high: Decimal
    low: Decimal
    close: Decimal
    volume: Decimal

    @classmethod
    def from_tick(
        cls, tick: MarketTick, interval: CandleInterval, bucket: CandleBucket
    ) -> _ActiveCandle:
        return cls(
            symbol=tick.symbol,
            interval=interval,
            bucket=bucket,
            open=tick.price,
            high=tick.price,
            low=tick.price,
            close=tick.price,
            volume=tick.trade_size,
        )

    def apply(self, tick: MarketTick) -> None:
        self.high = max(self.high, tick.price)
        self.low = min(self.low, tick.price)
        self.close = tick.price
        self.volume += tick.trade_size

    def to_candle(self, *, is_complete: bool) -> Candle:
        return Candle(
            symbol=self.symbol,
            interval=self.interval,
            start_at=self.bucket.start_at,
            end_at=self.bucket.end_at,
            open=self.open,
            high=self.high,
            low=self.low,
            close=self.close,
            volume=self.volume,
            is_complete=is_complete,
        )


class CandleEngine:
    """Aggregates regular-session ticks without creating synthetic or future candles."""

    def __init__(self, settings: CandleEngineSettings, calendar: XnysExchangeCalendar) -> None:
        if not settings.intervals:
            raise ValueError("at least one candle interval must be configured")
        if len(set(settings.intervals)) != len(settings.intervals):
            raise ValueError("candle intervals must be unique")
        self._settings = settings
        self._calendar = calendar
        self._active: dict[tuple[str, CandleInterval], _ActiveCandle] = {}
        self._latest_timestamp_by_symbol: dict[str, datetime] = {}
        self._lock = asyncio.Lock()

    async def process_tick(self, tick: MarketTick) -> CandleUpdate:
        """Apply a tick to all enabled intervals using only its known event time."""
        async with self._lock:
            latest_timestamp = self._latest_timestamp_by_symbol.get(tick.symbol)
            if latest_timestamp is not None and tick.timestamp < latest_timestamp:
                return CandleUpdate(ignored=True, reason="timestamp_precedes_symbol_watermark")

            updated: list[Candle] = []
            completed: list[Candle] = []
            for interval in self._settings.intervals:
                bucket = self._calendar.bucket_for(tick.timestamp, interval)
                if bucket is None:
                    continue
                key = (tick.symbol, interval)
                active = self._active.get(key)
                if active is not None and bucket.start_at > active.bucket.start_at:
                    completed.append(active.to_candle(is_complete=True))
                    active = None
                if active is None:
                    active = _ActiveCandle.from_tick(tick, interval, bucket)
                    self._active[key] = active
                else:
                    active.apply(tick)
                updated.append(active.to_candle(is_complete=False))

            self._latest_timestamp_by_symbol[tick.symbol] = tick.timestamp
            if not updated:
                return CandleUpdate(ignored=True, reason="outside_regular_trading_session")
            return CandleUpdate(updated=tuple(updated), completed=tuple(completed))

    async def finalize_through(self, as_of: datetime) -> CandleUpdate:
        """Complete bars whose end is known to be no later than ``as_of``."""
        if as_of.tzinfo is None or as_of.utcoffset() is None:
            raise ValueError("as_of must be timezone-aware")
        cutoff = as_of.astimezone(UTC)
        async with self._lock:
            completed = [
                active.to_candle(is_complete=True)
                for active in self._active.values()
                if active.bucket.end_at <= cutoff
            ]
            for candle in completed:
                del self._active[(candle.symbol, candle.interval)]
            return CandleUpdate(completed=tuple(completed))
