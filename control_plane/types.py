"""Versioned, operator-facing trading configuration values."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from config.settings import TradingMode
from market_data.types import CandleInterval
from risk.types import RiskPolicy


class EmaStrategyConfiguration(BaseModel):
    """Configurable parameters for the currently available EMA strategy."""

    model_config = ConfigDict(frozen=True)

    name: str = "ema_crossover"
    interval: CandleInterval = CandleInterval.ONE_MINUTE
    fast_period: int = Field(default=12, ge=2, le=500)
    slow_period: int = Field(default=26, ge=3, le=1_000)
    base_confidence: Decimal = Field(default=Decimal("0.60"), ge=Decimal(0), le=Decimal(1))
    confidence_sensitivity: Decimal = Field(default=Decimal(10), gt=Decimal(0))
    max_confidence: Decimal = Field(default=Decimal("0.95"), ge=Decimal(0), le=Decimal(1))

    @model_validator(mode="after")
    def validate_ema_configuration(self) -> EmaStrategyConfiguration:
        if self.name != "ema_crossover":
            raise ValueError("only ema_crossover is currently available")
        if self.fast_period >= self.slow_period:
            raise ValueError("fast_period must be lower than slow_period")
        if self.max_confidence < self.base_confidence:
            raise ValueError("max_confidence cannot be below base_confidence")
        return self


class RuntimeTradingConfiguration(BaseModel):
    """The complete durable configuration applied to trading workers."""

    model_config = ConfigDict(frozen=True)

    mode: TradingMode = TradingMode.PAPER
    place_orders_automatically: bool = False
    monitoring_enabled: bool = True
    symbols: tuple[Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")], ...] = ()
    strategy: EmaStrategyConfiguration = Field(default_factory=EmaStrategyConfiguration)
    risk_policy: RiskPolicy
    version: int = Field(default=1, ge=1)
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("symbols", mode="before")
    @classmethod
    def normalize_symbols(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            values = value.split(",")
        elif isinstance(value, (list, tuple)):
            values = value
        else:
            raise TypeError("symbols must be a sequence or comma-separated string")
        symbols = tuple(str(symbol).strip().upper() for symbol in values if str(symbol).strip())
        if len(symbols) != len(set(symbols)):
            raise ValueError("symbols must be unique")
        return symbols

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        return value.astimezone(UTC)


class TradingConfigurationUpdate(BaseModel):
    """Optimistic-concurrency update submitted by the dashboard."""

    model_config = ConfigDict(frozen=True)

    mode: TradingMode
    place_orders_automatically: bool
    monitoring_enabled: bool
    symbols: tuple[str, ...]
    strategy: EmaStrategyConfiguration
    risk_policy: RiskPolicy
    expected_version: int = Field(ge=1)
    live_confirmation: str | None = Field(default=None, max_length=64)
    automation_confirmation: str | None = Field(default=None, max_length=64)

    def to_configuration(self, *, version: int) -> RuntimeTradingConfiguration:
        return RuntimeTradingConfiguration(
            mode=self.mode,
            place_orders_automatically=self.place_orders_automatically,
            monitoring_enabled=self.monitoring_enabled,
            symbols=self.symbols,
            strategy=self.strategy,
            risk_policy=self.risk_policy,
            version=version,
        )


class TradingConfigurationAudit(BaseModel):
    """Immutable record of an applied runtime configuration version."""

    model_config = ConfigDict(frozen=True)

    version: int
    configuration: RuntimeTradingConfiguration
    created_at: datetime
