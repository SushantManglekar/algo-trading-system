from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from market_data.types import Candle, CandleInterval, MarketTick
from strategies.contracts import Strategy
from strategies.engine import StrategyEngine
from strategies.exceptions import DuplicateStrategyError, StrategyLifecycleError
from strategies.registry import StrategyRegistry
from strategies.types import StrategyDirection, StrategySignalIntent


def market_tick() -> MarketTick:
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


def candle() -> Candle:
    tick = market_tick()
    return Candle(
        symbol=tick.symbol,
        interval=CandleInterval.ONE_MINUTE,
        start_at=tick.timestamp,
        end_at=tick.timestamp + timedelta(minutes=1),
        open=tick.price,
        high=tick.price,
        low=tick.price,
        close=tick.price,
        volume=tick.trade_size,
        is_complete=True,
    )


class RecordingStrategy(Strategy):
    def __init__(self, name: str, *, fail_on_tick: bool = False, fail_initialize: bool = False) -> None:
        self._name = name
        self._fail_on_tick = fail_on_tick
        self._fail_initialize = fail_initialize
        self.initialized = False
        self.reset_count = 0
        self.events: list[str] = []
        self._intent: StrategySignalIntent | None = None

    @property
    def name(self) -> str:
        return self._name

    async def initialize(self) -> None:
        if self._fail_initialize:
            raise RuntimeError("initialization failure")
        self.initialized = True

    async def on_tick(self, tick: MarketTick) -> None:
        if self._fail_on_tick:
            raise RuntimeError("tick failure")
        self.events.append("tick")
        self._intent = StrategySignalIntent(
            symbol=tick.symbol,
            timestamp=tick.timestamp,
            strategy=self.name,
            direction=StrategyDirection.BUY,
            confidence=Decimal("0.75"),
            reason="test tick",
        )

    async def on_candle(self, received_candle: Candle) -> None:
        self.events.append("candle")
        self._intent = StrategySignalIntent(
            symbol=received_candle.symbol,
            timestamp=received_candle.end_at,
            strategy=self.name,
            direction=StrategyDirection.HOLD,
            confidence=Decimal("0.50"),
            reason="test candle",
        )

    async def generate_signal(self) -> StrategySignalIntent | None:
        return self._intent

    async def reset(self) -> None:
        self.initialized = False
        self._intent = None
        self.reset_count += 1


@pytest.mark.asyncio
async def test_engine_dispatches_tick_and_candle_to_multiple_isolated_strategies() -> None:
    first = RecordingStrategy("first")
    second = RecordingStrategy("second")
    registry = StrategyRegistry()
    registry.register(first)
    registry.register(second)
    engine = StrategyEngine(registry)
    await engine.initialize()

    tick_result = await engine.on_tick(market_tick())
    candle_result = await engine.on_candle(candle())

    assert [intent.strategy for intent in tick_result.intents] == ["first", "second"]
    assert {intent.direction for intent in candle_result.intents} == {StrategyDirection.HOLD}
    assert first.events == ["tick", "candle"]
    assert second.events == ["tick", "candle"]


@pytest.mark.asyncio
async def test_strategy_failure_is_contained_without_stopping_other_plugins() -> None:
    failing = RecordingStrategy("failing", fail_on_tick=True)
    healthy = RecordingStrategy("healthy")
    registry = StrategyRegistry()
    registry.register(failing)
    registry.register(healthy)
    engine = StrategyEngine(registry)
    await engine.initialize()

    result = await engine.on_tick(market_tick())

    assert [failure.strategy for failure in result.failures] == ["failing"]
    assert [intent.strategy for intent in result.intents] == ["healthy"]


@pytest.mark.asyncio
async def test_engine_requires_lifecycle_and_resets_initialized_plugins_after_setup_failure() -> None:
    healthy = RecordingStrategy("healthy")
    broken = RecordingStrategy("broken", fail_initialize=True)
    registry = StrategyRegistry()
    registry.register(healthy)
    registry.register(broken)
    engine = StrategyEngine(registry)

    with pytest.raises(StrategyLifecycleError, match="initialization failed"):
        await engine.initialize()
    assert healthy.reset_count == 1

    with pytest.raises(StrategyLifecycleError, match="not initialized"):
        await engine.on_tick(market_tick())


def test_registry_rejects_duplicate_strategy_names() -> None:
    registry = StrategyRegistry()
    registry.register(RecordingStrategy("same"))

    with pytest.raises(DuplicateStrategyError, match="already registered"):
        registry.register(RecordingStrategy("same"))
