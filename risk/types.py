"""Risk-policy inputs and immutable, risk-managed signal outcomes."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from strategies.types import StrategyDirection, StrategySignalIntent

PositiveAmount = Annotated[Decimal, Field(gt=Decimal(0), max_digits=18, decimal_places=8)]
NonNegativeAmount = Annotated[Decimal, Field(ge=Decimal(0), max_digits=18, decimal_places=8)]


class RiskDecisionStatus(StrEnum):
    """Terminal outcome of pre-trade risk evaluation."""

    APPROVED = "approved"
    REJECTED = "rejected"
    NOT_APPLICABLE = "not_applicable"


class RiskPolicy(BaseModel):
    """Configurable capital-preservation limits applied to every proposed entry."""

    model_config = ConfigDict(frozen=True)

    risk_per_trade_fraction: Annotated[Decimal, Field(gt=Decimal(0), le=Decimal(1))]
    max_daily_loss_fraction: Annotated[Decimal, Field(gt=Decimal(0), le=Decimal(1))]
    max_consecutive_losses: Annotated[int, Field(ge=1, le=100)]
    stop_atr_multiple: Annotated[Decimal, Field(gt=Decimal(0), max_digits=8, decimal_places=3)]
    target_atr_multiple: Annotated[Decimal, Field(gt=Decimal(0), max_digits=8, decimal_places=3)]
    trailing_stop_atr_multiple: Annotated[Decimal, Field(gt=Decimal(0), max_digits=8, decimal_places=3)]
    minimum_risk_reward: Annotated[Decimal, Field(ge=Decimal(1), max_digits=6, decimal_places=3)]

    @model_validator(mode="after")
    def validate_reward_policy(self) -> RiskPolicy:
        if self.target_atr_multiple / self.stop_atr_multiple < self.minimum_risk_reward:
            raise ValueError("target ATR multiple must satisfy minimum risk-reward")
        return self


class RiskContext(BaseModel):
    """Known account and market state at the instant a strategy intent is evaluated."""

    model_config = ConfigDict(frozen=True)

    entry_price: PositiveAmount
    atr: PositiveAmount
    account_equity: PositiveAmount
    daily_realized_pnl: Decimal
    consecutive_losses: Annotated[int, Field(ge=0)]
    would_average_down: bool = False


class RiskManagedSignal(BaseModel):
    """A fully sized entry proposal; never an order or execution instruction."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    timestamp: datetime
    strategy: str
    direction: StrategyDirection
    entry_price: PositiveAmount
    stop_loss: PositiveAmount
    take_profit: PositiveAmount
    atr_stop_loss: PositiveAmount
    trailing_stop_distance: PositiveAmount
    risk_reward: Annotated[Decimal, Field(ge=Decimal(1), max_digits=8, decimal_places=3)]
    position_size: Annotated[int, Field(ge=1)]
    position_risk: PositiveAmount
    expected_move: PositiveAmount
    confidence: Annotated[Decimal, Field(ge=Decimal(0), le=Decimal(1), max_digits=4)]
    reason: str

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)


class RiskDecision(BaseModel):
    """A transparent risk decision, including a rejection reason when blocked."""

    model_config = ConfigDict(frozen=True)

    status: RiskDecisionStatus
    intent: StrategySignalIntent
    signal: RiskManagedSignal | None = None
    reason: str | None = None

    @model_validator(mode="after")
    def validate_outcome(self) -> RiskDecision:
        if self.status is RiskDecisionStatus.APPROVED and self.signal is None:
            raise ValueError("approved decisions require a managed signal")
        if self.status is not RiskDecisionStatus.APPROVED and self.signal is not None:
            raise ValueError("non-approved decisions cannot include a managed signal")
        return self
