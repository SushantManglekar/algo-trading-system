import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from market_data.types import Candle, CandleInterval, HistoricalCandleRequest, MarketTick
from providers.exceptions import ProviderNotConnectedError
from providers.mock import MockMarketDataProvider, MockProviderSettings


def build_tick(symbol: str = "AAPL") -> MarketTick:
    timestamp = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)
    return MarketTick(
        timestamp=timestamp,
        received_at=timestamp + timedelta(milliseconds=5),
        symbol=symbol,
        exchange="NASDAQ",
        price=Decimal("200.01"),
        bid=Decimal("200.00"),
        ask=Decimal("200.02"),
        volume=Decimal(1000),
        trade_size=Decimal(100),
    )


def build_candle(
    start_at: datetime,
    *,
    symbol: str = "AAPL",
    is_complete: bool = True,
) -> Candle:
    return Candle(
        symbol=symbol,
        interval=CandleInterval.ONE_MINUTE,
        start_at=start_at,
        end_at=start_at + timedelta(minutes=1),
        open=Decimal("200.00"),
        high=Decimal("200.20"),
        low=Decimal("199.90"),
        close=Decimal("200.10"),
        volume=Decimal(1000),
        is_complete=is_complete,
    )


@pytest.mark.asyncio
async def test_mock_provider_streams_only_subscribed_ticks_and_stops_cleanly() -> None:
    provider = MockMarketDataProvider(MockProviderSettings(name="local-replay"))

    await provider.connect()
    await provider.subscribe(["aapl"])
    stream = provider.stream_ticks()
    next_tick = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)

    assert await provider.publish_tick(build_tick("MSFT")) is False
    assert await provider.publish_tick(build_tick("AAPL")) is True
    assert (await asyncio.wait_for(next_tick, timeout=0.2)).symbol == "AAPL"

    await provider.unsubscribe(["AAPL"])
    assert await provider.publish_tick(build_tick()) is False
    await provider.disconnect()

    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(stream), timeout=0.2)

    assert provider.is_connected is False
    assert provider.subscriptions == frozenset()


@pytest.mark.asyncio
async def test_mock_provider_filters_history_without_returning_incomplete_candles() -> None:
    start = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)
    provider = MockMarketDataProvider(
        historical_candles=(
            build_candle(start + timedelta(minutes=1)),
            build_candle(start),
            build_candle(start + timedelta(minutes=2), is_complete=False),
            build_candle(start, symbol="MSFT"),
        )
    )
    await provider.connect()

    candles = await provider.get_historical_candles(
        HistoricalCandleRequest(
            symbol="aapl",
            interval=CandleInterval.ONE_MINUTE,
            start_at=start,
            end_at=start + timedelta(minutes=3),
        )
    )

    assert [candle.start_at for candle in candles] == [start, start + timedelta(minutes=1)]


@pytest.mark.asyncio
async def test_mock_provider_rejects_operations_before_connecting() -> None:
    provider = MockMarketDataProvider()

    with pytest.raises(ProviderNotConnectedError, match="not connected"):
        await provider.subscribe(["AAPL"])
    with pytest.raises(ProviderNotConnectedError, match="not connected"):
        await provider.publish_tick(build_tick())
