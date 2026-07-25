"""Single market-event path shared by REST ingestion and background market-data workers."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from decimal import Decimal

from execution.service import AutomatedExecutionService
from market_data.candle_engine import CandleEngine
from market_data.candle_store import CandleStore
from market_data.tick_processor import TickProcessor
from market_data.types import Candle, CandleInterval, MarketTick
from risk.engine import RiskEngine
from signals.store import SignalStore
from strategies.engine import StrategyEngine
from strategies.types import StrategyDirection


class AtrTracker:
    """Per-series ATR using only completed candles that were known at evaluation time."""

    def __init__(self, period: int) -> None:
        self._period = period
        self._previous_close: dict[tuple[str, CandleInterval], Decimal] = {}
        self._ranges: dict[tuple[str, CandleInterval], deque[Decimal]] = {}

    def update(self, candle: Candle) -> Decimal | None:
        key = (candle.symbol, candle.interval)
        previous_close = self._previous_close.get(key)
        true_range = candle.high - candle.low
        if previous_close is not None:
            true_range = max(true_range, abs(candle.high - previous_close), abs(candle.low - previous_close))
        self._previous_close[key] = candle.close
        ranges = self._ranges.setdefault(key, deque(maxlen=self._period))
        ranges.append(true_range)
        if len(ranges) < self._period:
            return None
        return sum(ranges, Decimal(0)) / Decimal(len(ranges))


class TradingOrchestrator:
    """Validates ticks, persists candles, evaluates strategies, risk-checks, and executes safely."""

    def __init__(
        self,
        tick_processor: TickProcessor,
        candle_engine: CandleEngine,
        candle_store: CandleStore,
        signal_store: SignalStore,
        strategy_engines: Mapping[str, StrategyEngine],
        risk_engine: RiskEngine,
        execution_service: AutomatedExecutionService,
        atr_period: int,
        live_hub: object,
    ) -> None:
        self._tick_processor = tick_processor
        self._candle_engine = candle_engine
        self._candle_store = candle_store
        self._signal_store = signal_store
        self._strategy_engines = dict(strategy_engines)
        self._risk_engine = risk_engine
        self._execution_service = execution_service
        self._atr = AtrTracker(atr_period)
        self._live_hub = live_hub

    async def initialize(self) -> None:
        for engine in self._strategy_engines.values():
            await engine.initialize()

    async def process_tick(self, tick: MarketTick) -> tuple[bool, str | None, int, int]:
        processing = await self._tick_processor.process(tick)
        if not processing.accepted:
            return False, processing.reason, 0, 0
        candle_update = await self._candle_engine.process_tick(processing.tick)
        for candle in (*candle_update.updated, *candle_update.completed):
            await self._candle_store.upsert(candle)
        await self._live_hub.publish("ticks", "tick", processing.tick.model_dump(mode="json"))
        for candle in candle_update.updated:
            await self._live_hub.publish("candles", "candle_updated", candle.model_dump(mode="json"))
        for candle in candle_update.completed:
            await self._live_hub.publish("candles", "candle_completed", candle.model_dump(mode="json"))
            await self._evaluate_completed_candle(candle)
        return True, None, len(candle_update.updated), len(candle_update.completed)

    async def _evaluate_completed_candle(self, candle: Candle) -> None:
        atr = self._atr.update(candle)
        engine = self._strategy_engines.get(candle.symbol)
        if engine is None:
            return
        dispatch = await engine.on_candle(candle)
        for intent in dispatch.intents:
            if intent.direction is StrategyDirection.HOLD:
                continue
            if intent.direction is StrategyDirection.EXIT:
                await self._execution_service.execute_exit(intent)
                continue
            if atr is None:
                await self._live_hub.publish(
                    "signals",
                    "risk_decision",
                    {"status": "rejected", "intent": intent.model_dump(mode="json"), "reason": "atr_not_ready"},
                )
                continue
            context = await self._execution_service.risk_context(
                entry_price=candle.close, atr=atr, symbol=intent.symbol
            )
            decision = self._risk_engine.evaluate(intent, context)
            if decision.signal is not None:
                await self._signal_store.append(decision.signal)
                await self._execution_service.execute_entry(decision.signal)
            await self._live_hub.publish("signals", "risk_decision", decision.model_dump(mode="json"))
