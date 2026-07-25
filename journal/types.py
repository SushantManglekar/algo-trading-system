"""Validated manual trade journal values, intentionally separate from broker execution."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class ManualTradeSide(StrEnum):
    BUY = "BUY"
    SELL = "SELL"


class ManualTradeStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"


class ManualTrade(BaseModel):
    """A user-entered journal entry, never an instruction to submit an order."""

    model_config = ConfigDict(frozen=True, str_strip_whitespace=True)

    trade_id: UUID = Field(default_factory=uuid4)
    symbol: Annotated[str, Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")]
    side: ManualTradeSide
    status: ManualTradeStatus = ManualTradeStatus.OPEN
    entry_at: datetime
    entry_price: Annotated[Decimal, Field(gt=Decimal(0), max_digits=18, decimal_places=8)]
    quantity: Annotated[Decimal, Field(gt=Decimal(0), max_digits=20, decimal_places=8)]
    exit_at: datetime | None = None
    exit_price: Annotated[Decimal | None, Field(gt=Decimal(0), max_digits=18, decimal_places=8)] = None
    notes: Annotated[str | None, Field(max_length=4_000)] = None
    tags: tuple[Annotated[str, Field(min_length=1, max_length=64)], ...] = ()
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("symbol", mode="before")
    @classmethod
    def normalize_symbol(cls, value: str) -> str:
        return value.upper()

    @field_validator("entry_at", "exit_at", "created_at", "updated_at")
    @classmethod
    def normalize_timestamp(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("timestamps must be timezone-aware")
        return value.astimezone(UTC)

    @model_validator(mode="after")
    def validate_close(self) -> ManualTrade:
        close_complete = self.exit_at is not None and self.exit_price is not None
        if self.status is ManualTradeStatus.CLOSED and not close_complete:
            raise ValueError("closed manual trades require exit_at and exit_price")
        if self.status is ManualTradeStatus.OPEN and (self.exit_at is not None or self.exit_price is not None):
            raise ValueError("open manual trades cannot have exit details")
        if self.exit_at is not None and self.exit_at < self.entry_at:
            raise ValueError("exit_at cannot precede entry_at")
        return self
