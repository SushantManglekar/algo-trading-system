"""Lifecycle and event dispatch service for isolated strategy plugins."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable

from market_data.types import Candle, MarketTick
from strategies.contracts import Strategy
from strategies.exceptions import StrategyLifecycleError
from strategies.registry import StrategyRegistry
from strategies.types import StrategyDispatchResult, StrategyFailure, StrategySignalIntent

EventHandler = Callable[[Strategy], Awaitable[None]]


class StrategyEngine:
    """Serializes market events while containing failures to their individual plugin."""

    def __init__(self, registry: StrategyRegistry) -> None:
        self._registry = registry
        self._initialized = False
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize all registered plugins atomically from the caller's perspective."""
        async with self._lock:
            if self._initialized:
                return
            initialized: list[Strategy] = []
            try:
                for strategy in self._registry.all():
                    await strategy.initialize()
                    initialized.append(strategy)
            except Exception as error:
                for strategy in reversed(initialized):
                    await strategy.reset()
                raise StrategyLifecycleError("strategy initialization failed") from error
            self._initialized = True

    async def on_tick(self, tick: MarketTick) -> StrategyDispatchResult:
        """Dispatch a tick to every active strategy in deterministic order."""
        return await self._dispatch(tick.symbol, lambda strategy: strategy.on_tick(tick))

    async def on_candle(self, candle: Candle) -> StrategyDispatchResult:
        """Dispatch a candle to every active strategy in deterministic order."""
        return await self._dispatch(candle.symbol, lambda strategy: strategy.on_candle(candle))

    async def reset(self) -> None:
        """Reset every plugin and return the engine to its pre-initialized state."""
        async with self._lock:
            for strategy in self._registry.all():
                await strategy.reset()
            self._initialized = False

    async def _dispatch(
        self, symbol: str, handler: EventHandler
    ) -> StrategyDispatchResult:
        async with self._lock:
            if not self._initialized:
                raise StrategyLifecycleError("strategy engine is not initialized")
            intents: list[StrategySignalIntent] = []
            failures: list[StrategyFailure] = []
            for strategy in self._registry.all():
                try:
                    await handler(strategy)
                    intent = await strategy.generate_signal()
                    if intent is not None:
                        if intent.strategy != strategy.name:
                            raise ValueError("strategy intent attribution does not match plugin name")
                        if intent.symbol != symbol:
                            raise ValueError("strategy intent symbol does not match dispatched event")
                        intents.append(intent)
                except Exception as error:  # noqa: BLE001 - plugin failures are intentionally isolated.
                    failures.append(
                        StrategyFailure(
                            strategy=strategy.name,
                            error_type=type(error).__name__,
                            message=str(error),
                        )
                    )
            return StrategyDispatchResult(intents=tuple(intents), failures=tuple(failures))
