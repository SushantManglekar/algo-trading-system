"""Historical-candle retrieval with a safe tick-aggregation fallback."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum

from market_data.candle_engine import CandleEngine, CandleEngineSettings
from market_data.exchange_calendar import XnysExchangeCalendar
from market_data.provider import MarketDataProvider
from market_data.types import Candle, HistoricalCandleRequest, MarketTick


class HistoricalCandleSource(StrEnum):
    """The source used to satisfy a historical candle request."""

    PROVIDER = "provider"
    TICK_AGGREGATION = "tick_aggregation"


@dataclass(frozen=True, slots=True)
class HistoricalCandleResult:
    """Historical candles plus an explicit provenance record."""

    candles: tuple[Candle, ...]
    source: HistoricalCandleSource


class HistoricalCandleService:
    """Uses vendor history when available and never fabricates partial fallback bars."""

    def __init__(self, calendar: XnysExchangeCalendar) -> None:
        self._calendar = calendar

    async def get_candles(
        self,
        request: HistoricalCandleRequest,
        provider: MarketDataProvider,
        fallback_ticks: Sequence[MarketTick],
    ) -> HistoricalCandleResult:
        provider_candles = tuple(await provider.get_historical_candles(request))
        if provider_candles:
            self._validate_provider_candles(provider_candles, request)
            return HistoricalCandleResult(
                candles=provider_candles,
                source=HistoricalCandleSource.PROVIDER,
            )

        engine = CandleEngine(
            CandleEngineSettings(intervals=(request.interval,)), self._calendar
        )
        for tick in sorted(fallback_ticks, key=lambda item: item.timestamp):
            if request.symbol == tick.symbol and request.start_at <= tick.timestamp < request.end_at:
                await engine.process_tick(tick)
        completed = (await engine.finalize_through(request.end_at)).completed
        candles = tuple(
            candle
            for candle in completed
            if candle.symbol == request.symbol
            and candle.interval == request.interval
            and candle.start_at >= request.start_at
            and candle.end_at <= request.end_at
        )
        return HistoricalCandleResult(
            candles=candles,
            source=HistoricalCandleSource.TICK_AGGREGATION,
        )

    @staticmethod
    def _validate_provider_candles(
        candles: Sequence[Candle], request: HistoricalCandleRequest
    ) -> None:
        if list(candles) != sorted(candles, key=lambda candle: candle.start_at):
            raise ValueError("provider candles must be ordered by ascending start_at")
        for candle in candles:
            if (
                candle.symbol != request.symbol
                or candle.interval != request.interval
                or not candle.is_complete
                or candle.start_at < request.start_at
                or candle.end_at > request.end_at
            ):
                raise ValueError("provider returned a candle outside the requested complete range")
