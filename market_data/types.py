"""Timestamp-safe market-data value objects shared across provider adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

Price = Annotated[Decimal, Field(gt=Decimal(0), max_digits=18, decimal_places=8)]
NonNegativeDecimal = Annotated[Decimal, Field(ge=Decimal(0), max_digits=22, decimal_places=8)]
PositiveDecimal = Annotated[Decimal, Field(gt=Decimal(0), max_digits=22, decimal_places=8)]


class CandleInterval(StrEnum):
    """Supported aggregation intervals; calendar intervals require session-aware handling."""

    ONE_MINUTE = "1m"
    TWO_MINUTES = "2m"
    THREE_MINUTES = "3m"
    FIVE_MINUTES = "5m"
    TEN_MINUTES = "10m"
    FIFTEEN_MINUTES = "15m"
    THIRTY_MINUTES = "30m"
    FORTY_FIVE_MINUTES = "45m"
    ONE_HOUR = "1h"
    TWO_HOURS = "2h"
    FOUR_HOURS = "4h"
    DAILY = "1d"
    WEEKLY = "1w"
    MONTHLY = "1mo"


class MarketTick(BaseModel):
    """A normalized trade tick, containing only information known when it was received."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    timestamp: datetime
    received_at: datetime
    symbol: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")]
    exchange: Annotated[str, Field(min_length=1, max_length=32)]
    price: Price
    bid: Price
    ask: Price
    volume: NonNegativeDecimal
    trade_size: PositiveDecimal
    conditions: tuple[str, ...] = ()

    @field_validator("timestamp", "received_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("exchange", mode="before")
    @classmethod
    def normalize_exchange(cls, value: str) -> str:
        return value.upper()

    @model_validator(mode="after")
    def validate_quote(self) -> MarketTick:
        if self.ask < self.bid:
            raise ValueError("ask must be greater than or equal to bid")
        return self

    @computed_field(return_type=Decimal)
    @property
    def spread(self) -> Decimal:
        """The contemporaneous ask-minus-bid spread, never provider-supplied guesswork."""
        return self.ask - self.bid

    @computed_field(return_type=int)
    @property
    def latency_ms(self) -> int:
        """Ingress latency derived from the event and receipt timestamps."""
        return max(0, int((self.received_at - self.timestamp).total_seconds() * 1_000))


class Candle(BaseModel):
    """A completed or in-progress OHLCV bar with an explicit availability timestamp."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    symbol: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")]
    interval: CandleInterval
    start_at: datetime
    end_at: datetime
    open: Price
    high: Price
    low: Price
    close: Price
    volume: NonNegativeDecimal
    is_complete: bool

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_ohlcv(self) -> Candle:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        if self.high < max(self.open, self.close) or self.low > min(self.open, self.close):
            raise ValueError("OHLC values are inconsistent")
        return self


class HistoricalCandleRequest(BaseModel):
    """A provider-neutral historical-candle query bounded by known timestamps."""

    model_config = ConfigDict(frozen=True)

    symbol: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")]
    interval: CandleInterval
    start_at: datetime
    end_at: datetime
    adjusted: bool = True

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("start_at", "end_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_range(self) -> HistoricalCandleRequest:
        if self.end_at <= self.start_at:
            raise ValueError("end_at must be after start_at")
        return self
