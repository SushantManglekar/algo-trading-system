"""Immutable outcome records and reporting schemas for signal analytics."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from risk.types import RiskManagedSignal
from strategies.types import StrategyDirection


class ClosedSignalOutcome(BaseModel):
    """Recorded result of a risk-managed signal after an externally observed close."""

    model_config = ConfigDict(frozen=True)

    outcome_id: UUID = Field(default_factory=uuid4)
    signal: RiskManagedSignal
    exit_price: Annotated[Decimal, Field(gt=Decimal(0), max_digits=18, decimal_places=8)]
    closed_at: datetime

    @field_validator("closed_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("closed_at must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_closed_signal(self) -> ClosedSignalOutcome:
        if self.signal.direction not in {StrategyDirection.BUY, StrategyDirection.SELL}:
            raise ValueError("only directional entry signals can have a closed outcome")
        if self.closed_at < self.signal.timestamp:
            raise ValueError("closed_at cannot precede the signal timestamp")
        return self

    @computed_field(return_type=Decimal)
    @property
    def realized_pnl(self) -> Decimal:
        price_move = (
            self.exit_price - self.signal.entry_price
            if self.signal.direction is StrategyDirection.BUY
            else self.signal.entry_price - self.exit_price
        )
        return price_move * self.signal.position_size

    @computed_field(return_type=Decimal)
    @property
    def r_multiple(self) -> Decimal:
        return self.realized_pnl / self.signal.position_risk

    @computed_field(return_type=Decimal)
    @property
    def holding_seconds(self) -> Decimal:
        return Decimal(str((self.closed_at - self.signal.timestamp).total_seconds()))


class AnalyticsSettings(BaseModel):
    """Explicit reporting and risk-free assumptions for trade-level analytics."""

    model_config = ConfigDict(frozen=True)

    starting_equity: Annotated[Decimal, Field(gt=Decimal(0), max_digits=18, decimal_places=2)]
    reporting_timezone: str
    risk_free_return_per_trade: Decimal = Decimal(0)


class PerformanceStatistics(BaseModel):
    """A statistics snapshot for all or one calendar reporting period."""

    model_config = ConfigDict(frozen=True)

    total_signals: int
    winning_signals: int
    losing_signals: int
    win_rate: Decimal | None
    average_gain: Decimal | None
    average_loss: Decimal | None
    profit_factor: Decimal | None
    sharpe_ratio: Decimal | None
    expectancy: Decimal | None
    average_holding_seconds: Decimal | None
    maximum_drawdown: Decimal
    maximum_drawdown_fraction: Decimal
    average_r_multiple: Decimal | None


class PeriodStatistics(BaseModel):
    """One daily, weekly, or monthly analytics partition."""

    model_config = ConfigDict(frozen=True)

    period: str
    statistics: PerformanceStatistics


class AnalyticsSnapshot(BaseModel):
    """Overall and periodized analytics for all recorded closed signal outcomes."""

    model_config = ConfigDict(frozen=True)

    overall: PerformanceStatistics
    daily: tuple[PeriodStatistics, ...]
    weekly: tuple[PeriodStatistics, ...]
    monthly: tuple[PeriodStatistics, ...]
