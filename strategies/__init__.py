"""Isolated trading-signal strategy plugins."""

from strategies.contracts import Strategy
from strategies.ema_crossover import EmaCrossoverSettings, EmaCrossoverStrategy
from strategies.engine import StrategyEngine
from strategies.registry import StrategyRegistry
from strategies.types import (
    StrategyDirection,
    StrategyDispatchResult,
    StrategyFailure,
    StrategySignalIntent,
)

__all__ = [
    "EmaCrossoverSettings",
    "EmaCrossoverStrategy",
    "Strategy",
    "StrategyDirection",
    "StrategyDispatchResult",
    "StrategyEngine",
    "StrategyFailure",
    "StrategyRegistry",
    "StrategySignalIntent",
]
