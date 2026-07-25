from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from market_data.candle_engine import CandleEngine, CandleEngineSettings
from market_data.exchange_calendar import XnysExchangeCalendar
from market_data.types import CandleInterval, MarketTick


def build_tick(timestamp: datetime, price: str, trade_size: str = "100") -> MarketTick:
    return MarketTick(
        timestamp=timestamp,
        received_at=timestamp + timedelta(milliseconds=4),
        symbol="AAPL",
        exchange="NASDAQ",
        price=Decimal(price),
        bid=Decimal("199.99"),
        ask=Decimal("200.01"),
        volume=Decimal(1000),
        trade_size=Decimal(trade_size),
    )


@pytest.mark.asyncio
async def test_candle_engine_builds_and_completes_session_aligned_five_minute_candles() -> None:
    engine = CandleEngine(
        CandleEngineSettings(intervals=(CandleInterval.FIVE_MINUTES,)),
        XnysExchangeCalendar(),
    )
    session_open = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)

    first = await engine.process_tick(build_tick(session_open + timedelta(seconds=15), "200.00"))
    second = await engine.process_tick(build_tick(session_open + timedelta(minutes=2), "200.20", "50"))
    transition = await engine.process_tick(build_tick(session_open + timedelta(minutes=5), "200.10"))

    assert first.updated[0].is_complete is False
    assert second.updated[0].high == Decimal("200.20")
    assert second.updated[0].volume == Decimal(150)
    completed = transition.completed[0]
    assert completed.is_complete is True
    assert completed.start_at == session_open
    assert completed.end_at == session_open + timedelta(minutes=5)
    assert completed.open == Decimal("200.00")
    assert completed.close == Decimal("200.20")
    assert transition.updated[0].start_at == session_open + timedelta(minutes=5)


@pytest.mark.asyncio
async def test_candle_engine_supports_every_requested_interval_and_rejects_weekend_ticks() -> None:
    engine = CandleEngine(
        CandleEngineSettings(intervals=tuple(CandleInterval)),
        XnysExchangeCalendar(),
    )
    regular_session_tick = build_tick(datetime(2026, 7, 24, 14, 0, tzinfo=UTC), "200.00")

    update = await engine.process_tick(regular_session_tick)
    assert {candle.interval for candle in update.updated} == set(CandleInterval)

    weekend = await engine.process_tick(
        build_tick(datetime(2026, 7, 25, 14, 0, tzinfo=UTC), "200.00")
    )
    assert weekend.ignored is True
    assert weekend.reason == "outside_regular_trading_session"


@pytest.mark.asyncio
async def test_candle_engine_finalizes_only_with_an_explicit_time_watermark() -> None:
    engine = CandleEngine(
        CandleEngineSettings(intervals=(CandleInterval.ONE_HOUR,)),
        XnysExchangeCalendar(),
    )
    session_open = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
    await engine.process_tick(build_tick(session_open + timedelta(minutes=1), "200.00"))

    before_close = await engine.finalize_through(session_open + timedelta(minutes=59))
    at_close = await engine.finalize_through(session_open + timedelta(hours=1))

    assert before_close.completed == ()
    assert len(at_close.completed) == 1
    assert at_close.completed[0].is_complete is True


@pytest.mark.asyncio
async def test_candle_engine_never_mutates_a_candle_with_a_regressing_tick() -> None:
    engine = CandleEngine(
        CandleEngineSettings(intervals=(CandleInterval.ONE_MINUTE,)),
        XnysExchangeCalendar(),
    )
    newer = datetime(2026, 7, 24, 13, 31, tzinfo=UTC)
    await engine.process_tick(build_tick(newer, "200.00"))

    result = await engine.process_tick(build_tick(newer - timedelta(seconds=30), "199.00"))

    assert result.ignored is True
    assert result.reason == "timestamp_precedes_symbol_watermark"
