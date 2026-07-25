from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from market_data.types import Candle, CandleInterval, HistoricalCandleRequest, MarketTick


def test_market_tick_normalizes_and_derives_ingress_fields() -> None:
    event_time = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)
    tick = MarketTick(
        timestamp=event_time,
        received_at=event_time + timedelta(milliseconds=17),
        symbol="aapl",
        exchange="nasdaq",
        price=Decimal("200.01"),
        bid=Decimal("200.00"),
        ask=Decimal("200.02"),
        volume=Decimal(12345),
        trade_size=Decimal(100),
        conditions=("regular_sale",),
    )

    assert tick.symbol == "AAPL"
    assert tick.exchange == "NASDAQ"
    assert tick.spread == Decimal("0.02")
    assert tick.latency_ms == 17
    assert tick.model_dump()["spread"] == Decimal("0.02")


def test_market_tick_rejects_invalid_or_ambiguous_quote_data() -> None:
    timestamp = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)
    kwargs = {
        "timestamp": timestamp,
        "received_at": timestamp,
        "symbol": "AAPL",
        "exchange": "NASDAQ",
        "price": "200",
        "bid": "200.02",
        "ask": "200.01",
        "volume": "1",
        "trade_size": "1",
    }

    with pytest.raises(ValidationError, match="ask must"):
        MarketTick(**kwargs)

    kwargs["ask"] = "200.03"
    kwargs["timestamp"] = datetime(2026, 7, 25, 14, 30)  # noqa: DTZ001
    with pytest.raises(ValidationError, match="timezone-aware"):
        MarketTick(**kwargs)


def test_candle_and_historical_request_reject_time_range_errors() -> None:
    start = datetime(2026, 7, 25, 14, 30, tzinfo=UTC)
    with pytest.raises(ValidationError, match="end_at must be after"):
        HistoricalCandleRequest(
            symbol="aapl",
            interval=CandleInterval.ONE_MINUTE,
            start_at=start,
            end_at=start,
        )

    with pytest.raises(ValidationError, match="OHLC values are inconsistent"):
        Candle(
            symbol="AAPL",
            interval=CandleInterval.ONE_MINUTE,
            start_at=start,
            end_at=start + timedelta(minutes=1),
            open="100",
            high="99",
            low="98",
            close="100",
            volume="10",
            is_complete=True,
        )
