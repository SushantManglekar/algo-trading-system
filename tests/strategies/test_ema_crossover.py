from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from pydantic import ValidationError

from market_data.types import Candle, CandleInterval, MarketTick
from strategies.ema_crossover import EmaCrossoverSettings, EmaCrossoverStrategy
from strategies.engine import StrategyEngine
from strategies.registry import StrategyRegistry
from strategies.types import StrategyDirection


def settings(*, long_only: bool = True) -> EmaCrossoverSettings:
    return EmaCrossoverSettings(
        name="ema_2_3",
        symbol="aapl",
        interval=CandleInterval.ONE_MINUTE,
        fast_period=2,
        slow_period=3,
        long_only=long_only,
        base_confidence=Decimal("0.50"),
        confidence_sensitivity=Decimal(50),
        max_confidence=Decimal("0.90"),
    )


def candle(index: int, close: str, *, is_complete: bool = True) -> Candle:
    start = datetime(2026, 7, 24, 13, 30, tzinfo=UTC) + timedelta(minutes=index)
    price = Decimal(close)
    return Candle(
        symbol="AAPL",
        interval=CandleInterval.ONE_MINUTE,
        start_at=start,
        end_at=start + timedelta(minutes=1),
        open=price,
        high=price,
        low=price,
        close=price,
        volume=Decimal(100),
        is_complete=is_complete,
    )


def tick() -> MarketTick:
    timestamp = datetime(2026, 7, 24, 13, 30, tzinfo=UTC)
    return MarketTick(
        timestamp=timestamp,
        received_at=timestamp + timedelta(milliseconds=1),
        symbol="AAPL",
        exchange="NASDAQ",
        price=Decimal(200),
        bid=Decimal("199.99"),
        ask=Decimal("200.01"),
        volume=Decimal(100),
        trade_size=Decimal(10),
    )


@pytest.mark.asyncio
async def test_ema_crossover_uses_only_completed_candles_and_emits_buy_on_cross() -> None:
    strategy = EmaCrossoverStrategy(settings())
    await strategy.initialize()

    await strategy.on_candle(candle(0, "100", is_complete=False))
    assert await strategy.generate_signal() is None

    for index, close in enumerate(("100", "99", "98", "99")):
        await strategy.on_candle(candle(index, close))
        warmup_signal = await strategy.generate_signal()
        assert warmup_signal is not None
        assert warmup_signal.direction is StrategyDirection.HOLD

    await strategy.on_candle(candle(4, "101"))
    signal = await strategy.generate_signal()

    assert signal is not None
    assert signal.direction is StrategyDirection.BUY
    assert signal.confidence > Decimal("0.50")
    assert signal.metadata["fast_ema"] > signal.metadata["slow_ema"]
    assert await strategy.generate_signal() is None


@pytest.mark.asyncio
async def test_ema_crossover_emits_exit_or_short_sell_on_downward_cross() -> None:
    long_only_strategy = EmaCrossoverStrategy(settings(long_only=True))
    short_enabled_strategy = EmaCrossoverStrategy(settings(long_only=False))
    await long_only_strategy.initialize()
    await short_enabled_strategy.initialize()

    for index, close in enumerate(("100", "101", "102", "101", "99")):
        candidate = candle(index, close)
        await long_only_strategy.on_candle(candidate)
        await short_enabled_strategy.on_candle(candidate)

    long_only_signal = await long_only_strategy.generate_signal()
    short_enabled_signal = await short_enabled_strategy.generate_signal()
    assert long_only_signal is not None
    assert short_enabled_signal is not None
    assert long_only_signal.direction is StrategyDirection.EXIT
    assert short_enabled_signal.direction is StrategyDirection.SELL


@pytest.mark.asyncio
async def test_ema_crossover_integrates_with_framework_and_ignores_tick_events() -> None:
    strategy = EmaCrossoverStrategy(settings())
    registry = StrategyRegistry()
    registry.register(strategy)
    engine = StrategyEngine(registry)
    await engine.initialize()

    assert (await engine.on_tick(tick())).intents == ()
    candle_result = await engine.on_candle(candle(0, "100"))

    assert candle_result.intents[0].direction is StrategyDirection.HOLD


def test_ema_crossover_rejects_invalid_period_and_confidence_configuration() -> None:
    with pytest.raises(ValidationError, match="fast_period"):
        EmaCrossoverSettings(
            name="invalid",
            symbol="AAPL",
            interval=CandleInterval.ONE_MINUTE,
            fast_period=10,
            slow_period=10,
            base_confidence=Decimal("0.50"),
            confidence_sensitivity=Decimal(50),
            max_confidence=Decimal("0.90"),
        )
