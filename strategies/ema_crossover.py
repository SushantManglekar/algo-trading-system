"""Completed-candle EMA crossover strategy with no repainting or future inputs."""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from market_data.types import Candle, CandleInterval, MarketTick
from strategies.contracts import Strategy
from strategies.types import StrategyDirection, StrategySignalIntent


class EmaCrossoverSettings(BaseModel):
    """Runtime parameters for one EMA crossover strategy instance."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    name: str = "ema_crossover"
    symbol: str
    interval: CandleInterval
    fast_period: int = Field(ge=2, le=500)
    slow_period: int = Field(ge=3, le=1_000)
    long_only: bool = True
    base_confidence: Decimal = Field(ge=Decimal(0), le=Decimal(1), max_digits=4)
    confidence_sensitivity: Decimal = Field(gt=Decimal(0), max_digits=8, decimal_places=2)
    max_confidence: Decimal = Field(ge=Decimal(0), le=Decimal(1), max_digits=4)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_periods_and_confidence(self) -> EmaCrossoverSettings:
        if not self.name:
            raise ValueError("strategy name cannot be blank")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be lower than slow_period")
        if self.max_confidence < self.base_confidence:
            raise ValueError("max_confidence cannot be below base_confidence")
        return self


class EmaCrossoverStrategy(Strategy):
    """Signals a crossover only after a completed candle makes it observable."""

    def __init__(self, settings: EmaCrossoverSettings) -> None:
        self._settings = settings
        self._fast_ema: Decimal | None = None
        self._slow_ema: Decimal | None = None
        self._previous_spread: Decimal | None = None
        self._completed_candles = 0
        self._last_candle_end: datetime | None = None
        self._pending_intent: StrategySignalIntent | None = None

    @property
    def name(self) -> str:
        return self._settings.name

    async def initialize(self) -> None:
        await self.reset()

    async def on_tick(self, tick: MarketTick) -> None:
        """Ignore ticks: this strategy intentionally operates only on closed candles."""
        del tick

    async def on_candle(self, candle: Candle) -> None:
        self._pending_intent = None
        if (
            not candle.is_complete
            or candle.symbol != self._settings.symbol
            or candle.interval != self._settings.interval
            or (self._last_candle_end is not None and candle.end_at <= self._last_candle_end)
        ):
            return

        self._fast_ema = self._next_ema(self._fast_ema, candle.close, self._settings.fast_period)
        self._slow_ema = self._next_ema(self._slow_ema, candle.close, self._settings.slow_period)
        self._completed_candles += 1
        self._last_candle_end = candle.end_at
        spread = self._fast_ema - self._slow_ema

        if self._completed_candles <= self._settings.slow_period:
            self._previous_spread = spread
            self._pending_intent = self._hold_intent(candle, "warming_up")
            return

        direction = self._cross_direction(spread)
        self._previous_spread = spread
        if direction is None:
            self._pending_intent = self._hold_intent(candle, "no_ema_crossover")
            return
        self._pending_intent = StrategySignalIntent(
            symbol=candle.symbol,
            timestamp=candle.end_at,
            strategy=self.name,
            direction=direction,
            confidence=self._confidence(candle.close, spread),
            reason=f"EMA {self._settings.fast_period}/{self._settings.slow_period} crossover",
            metadata={
                "fast_ema": self._fast_ema,
                "slow_ema": self._slow_ema,
                "close": candle.close,
                "interval": candle.interval.value,
            },
        )

    async def generate_signal(self) -> StrategySignalIntent | None:
        intent, self._pending_intent = self._pending_intent, None
        return intent

    async def reset(self) -> None:
        self._fast_ema = None
        self._slow_ema = None
        self._previous_spread = None
        self._completed_candles = 0
        self._last_candle_end = None
        self._pending_intent = None

    def _cross_direction(self, current_spread: Decimal) -> StrategyDirection | None:
        if self._previous_spread is None:
            return None
        if self._previous_spread <= Decimal(0) < current_spread:
            return StrategyDirection.BUY
        if self._previous_spread >= Decimal(0) > current_spread:
            return StrategyDirection.EXIT if self._settings.long_only else StrategyDirection.SELL
        return None

    def _hold_intent(self, candle: Candle, reason: str) -> StrategySignalIntent:
        return StrategySignalIntent(
            symbol=candle.symbol,
            timestamp=candle.end_at,
            strategy=self.name,
            direction=StrategyDirection.HOLD,
            confidence=self._settings.base_confidence,
            reason=reason,
            metadata={
                "fast_ema": self._fast_ema,
                "slow_ema": self._slow_ema,
                "completed_candles": self._completed_candles,
            },
        )

    def _confidence(self, close: Decimal, spread: Decimal) -> Decimal:
        relative_separation = abs(spread) / close
        confidence = self._settings.base_confidence + (
            relative_separation * self._settings.confidence_sensitivity
        )
        return min(confidence, self._settings.max_confidence).quantize(
            Decimal("0.001"), rounding=ROUND_HALF_UP
        )

    @staticmethod
    def _next_ema(previous: Decimal | None, close: Decimal, period: int) -> Decimal:
        if previous is None:
            return close
        multiplier = Decimal(2) / Decimal(period + 1)
        return (close - previous) * multiplier + previous
