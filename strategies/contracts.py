"""Strategy plugin contract used by the framework and concrete strategies."""

from __future__ import annotations

from abc import ABC, abstractmethod

from market_data.types import Candle, MarketTick
from strategies.types import StrategySignalIntent


class Strategy(ABC):
    """An isolated stateful strategy plugin with an explicit lifecycle."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Return a stable unique name used for configuration and attribution."""

    @abstractmethod
    async def initialize(self) -> None:
        """Prepare strategy state before the framework begins dispatching events."""

    @abstractmethod
    async def on_tick(self, tick: MarketTick) -> None:
        """Consume a validated, chronologically safe tick."""

    @abstractmethod
    async def on_candle(self, candle: Candle) -> None:
        """Consume an updated or completed exchange-session candle."""

    @abstractmethod
    async def generate_signal(self) -> StrategySignalIntent | None:
        """Return the current decision without mutating future market state."""

    @abstractmethod
    async def reset(self) -> None:
        """Discard internal state, allowing deterministic re-initialization."""
