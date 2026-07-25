"""Provider-independent strategy intents and dispatch outcomes."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class StrategyDirection(StrEnum):
    """Permitted actions from a signal-generation strategy."""

    BUY = "BUY"
    SELL = "SELL"
    EXIT = "EXIT"
    HOLD = "HOLD"


class StrategySignalIntent(BaseModel):
    """A strategy's risk-unadjusted decision; risk enrichment occurs in Step 8."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    symbol: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")]
    timestamp: datetime
    strategy: Annotated[str, Field(min_length=1, max_length=128)]
    direction: StrategyDirection
    confidence: Annotated[Decimal, Field(ge=Decimal(0), le=Decimal(1), max_digits=4)]
    reason: Annotated[str, Field(min_length=1, max_length=1_000)]
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("timestamp")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamp must be timezone-aware")
        return value.astimezone(UTC)


class StrategyFailure(BaseModel):
    """A contained strategy exception, suitable for structured logging and metrics."""

    model_config = ConfigDict(frozen=True)

    strategy: str
    error_type: str
    message: str


class StrategyDispatchResult(BaseModel):
    """Signals and isolated errors produced while dispatching one market event."""

    model_config = ConfigDict(frozen=True)

    intents: tuple[StrategySignalIntent, ...] = ()
    failures: tuple[StrategyFailure, ...] = ()
