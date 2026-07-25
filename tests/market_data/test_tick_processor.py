import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from market_data.tick_processor import (
    TickProcessingStatus,
    TickProcessor,
    TickProcessorSettings,
)
from market_data.tick_store import InMemoryTickStore
from market_data.types import MarketTick
from providers.mock import MockMarketDataProvider


def tick_payload(timestamp: datetime, symbol: str = "AAPL") -> dict[str, object]:
    return {
        "timestamp": timestamp,
        "received_at": timestamp + timedelta(milliseconds=5),
        "symbol": symbol,
        "exchange": "NASDAQ",
        "price": "200.01",
        "bid": "200.00",
        "ask": "200.02",
        "volume": "1000",
        "trade_size": "100",
        "conditions": ("regular_sale",),
    }


@pytest.mark.asyncio
async def test_tick_processor_normalizes_persists_and_bounds_history() -> None:
    store = InMemoryTickStore(max_ticks_per_symbol=2)
    processor = TickProcessor(store, TickProcessorSettings())
    start = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)

    for minute in range(3):
        result = await processor.process(tick_payload(start + timedelta(minutes=minute), "aapl"))
        assert result.status is TickProcessingStatus.ACCEPTED

    ticks = await store.list_ticks("AAPL")
    assert [tick.timestamp for tick in ticks] == [
        start + timedelta(minutes=1),
        start + timedelta(minutes=2),
    ]
    latest = await store.latest("aapl")
    assert latest is not None
    assert latest.symbol == "AAPL"


@pytest.mark.asyncio
async def test_tick_processor_drops_timestamp_regressions_without_storing_them() -> None:
    store = InMemoryTickStore(max_ticks_per_symbol=10)
    processor = TickProcessor(store, TickProcessorSettings(reject_out_of_order_ticks=True))
    start = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)

    await processor.process(tick_payload(start + timedelta(seconds=1)))
    dropped = await processor.process(tick_payload(start))

    assert dropped.status is TickProcessingStatus.DROPPED_OUT_OF_ORDER
    assert dropped.reason == "timestamp_precedes_symbol_watermark"
    assert len(await store.list_ticks("AAPL")) == 1


@pytest.mark.asyncio
async def test_tick_processor_rejects_invalid_payloads_before_persistence() -> None:
    store = InMemoryTickStore(max_ticks_per_symbol=10)
    processor = TickProcessor(store, TickProcessorSettings())
    timestamp = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)
    invalid_payload = tick_payload(timestamp)
    invalid_payload["bid"] = Decimal("200.03")

    with pytest.raises(ValidationError, match="ask must"):
        await processor.process(invalid_payload)
    assert await store.latest("AAPL") is None


@pytest.mark.asyncio
async def test_tick_processor_consumes_a_live_provider_stream() -> None:
    provider = MockMarketDataProvider()
    store = InMemoryTickStore(max_ticks_per_symbol=10)
    processor = TickProcessor(store, TickProcessorSettings())
    timestamp = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)

    await provider.connect()
    await provider.subscribe(["AAPL"])
    consumption = processor.consume(provider)
    next_result = asyncio.create_task(anext(consumption))
    await asyncio.sleep(0)
    tick = MarketTick.model_validate(tick_payload(timestamp))
    assert await provider.publish_tick(tick) is True

    result = await asyncio.wait_for(next_result, timeout=0.2)
    assert result.accepted is True
    assert (await store.latest("AAPL")) == tick

    await provider.disconnect()
    with pytest.raises(StopAsyncIteration):
        await asyncio.wait_for(anext(consumption), timeout=0.2)
