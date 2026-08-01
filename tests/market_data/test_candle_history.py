from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from market_data.candle_history import HistoricalCandleService, HistoricalCandleSource
from market_data.exchange_calendar import XnysExchangeCalendar
from market_data.tick_chart import downsample_ticks
from market_data.types import Candle, CandleInterval, HistoricalCandleRequest, MarketTick
from providers.mock import MockMarketDataProvider


class InclusiveBoundaryProvider(MockMarketDataProvider):
    """Simulates a vendor whose historical end value is inclusive."""

    def __init__(self, candles: tuple[Candle, ...]) -> None:
        super().__init__()
        self._candles = candles

    async def get_historical_candles(
        self, request: HistoricalCandleRequest
    ) -> tuple[Candle, ...]:
        return self._candles


def candle(start_at: datetime) -> Candle:
    return Candle(
        symbol="AAPL",
        interval=CandleInterval.ONE_MINUTE,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=1),
        open=Decimal("200.00"),
        high=Decimal("200.10"),
        low=Decimal("199.90"),
        close=Decimal("200.05"),
        volume=Decimal(100),
        is_complete=True,
    )


def tick(timestamp: datetime) -> MarketTick:
    return MarketTick(
        timestamp=timestamp,
        received_at=timestamp + timedelta(milliseconds=2),
        symbol="AAPL",
        exchange="NASDAQ",
        price=Decimal("200.00"),
        bid=Decimal("199.99"),
        ask=Decimal("200.01"),
        volume=Decimal(100),
        trade_size=Decimal(100),
    )


@pytest.mark.asyncio
async def test_history_service_prefers_complete_provider_candles() -> None:
    start = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
    expected = candle(start)
    provider = MockMarketDataProvider(historical_candles=(expected,))
    await provider.connect()
    request = HistoricalCandleRequest(
        symbol="AAPL",
        interval=CandleInterval.ONE_MINUTE,
        start_at=start,
        end_at=start + timedelta(minutes=1),
    )

    result = await HistoricalCandleService(XnysExchangeCalendar()).get_candles(
        request, provider, fallback_ticks=()
    )

    assert result.source is HistoricalCandleSource.PROVIDER
    assert result.candles == (expected,)


@pytest.mark.asyncio
async def test_history_service_discards_provider_bar_at_inclusive_end_boundary() -> None:
    start = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
    expected = candle(start)
    provider = InclusiveBoundaryProvider((expected, candle(start + timedelta(minutes=1))))
    await provider.connect()
    request = HistoricalCandleRequest(
        symbol="AAPL",
        interval=CandleInterval.ONE_MINUTE,
        start_at=start,
        end_at=start + timedelta(minutes=1),
    )

    result = await HistoricalCandleService(XnysExchangeCalendar()).get_candles(
        request, provider, fallback_ticks=()
    )

    assert result.source is HistoricalCandleSource.PROVIDER
    assert result.candles == (expected,)


@pytest.mark.asyncio
async def test_history_service_aggregates_ticks_only_when_provider_has_no_history() -> None:
    start = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
    provider = MockMarketDataProvider()
    await provider.connect()
    request = HistoricalCandleRequest(
        symbol="AAPL",
        interval=CandleInterval.ONE_MINUTE,
        start_at=start,
        end_at=start + timedelta(minutes=1),
    )

    result = await HistoricalCandleService(XnysExchangeCalendar()).get_candles(
        request,
        provider,
        fallback_ticks=(tick(start + timedelta(seconds=40)), tick(start + timedelta(seconds=10))),
    )

    assert result.source is HistoricalCandleSource.TICK_AGGREGATION
    assert len(result.candles) == 1
    assert result.candles[0].is_complete is True
    assert result.candles[0].volume == Decimal(200)


def test_tick_chart_downsampling_keeps_order_and_range_endpoints() -> None:
    start = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
    ticks = tuple(tick(start + timedelta(seconds=index)) for index in range(100))

    sampled = downsample_ticks(ticks, max_points=12)

    assert len(sampled) == 12
    assert sampled[0] == ticks[0]
    assert sampled[-1] == ticks[-1]
    assert list(sampled) == sorted(sampled, key=lambda item: item.timestamp)
