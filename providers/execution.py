"""Broker-neutral execution boundary; implementations must enforce their own safety policy."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderLifecycleStatus(StrEnum):
    PENDING = "pending"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    REJECTED = "rejected"
    FAILED = "failed"


class AccountSnapshot(BaseModel):
    """Provider-neutral account state used to construct point-in-time risk context."""

    model_config = ConfigDict(frozen=True)

    account_id: str
    cash: Decimal = Field(ge=Decimal(0))
    equity: Decimal = Field(gt=Decimal(0))
    buying_power: Decimal = Field(ge=Decimal(0))
    previous_close_equity: Decimal | None = Field(default=None, gt=Decimal(0))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @field_validator("updated_at")
    @classmethod
    def normalize_updated_at(cls, value: datetime) -> datetime:
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("updated_at must be timezone-aware")
        return value.astimezone(UTC)

    @property
    def daily_pnl(self) -> Decimal:
        """Conservative daily mark-to-market P/L when the broker exposes prior-close equity."""
        if self.previous_close_equity is None:
            return Decimal(0)
        return self.equity - self.previous_close_equity


class PositionSnapshot(BaseModel):
    """Provider-neutral current holding for exposure, concentration, and P/L views."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    quantity: Decimal
    average_entry_price: Decimal = Field(gt=Decimal(0))
    market_value: Decimal
    cost_basis: Decimal
    unrealized_pnl: Decimal = Decimal(0)
    unrealized_pnl_percent: Decimal = Decimal(0)


class OrderRequest(BaseModel):
    """Idempotent order intent approved by risk controls, not a strategy signal."""

    model_config = ConfigDict(frozen=True)

    client_order_id: str = Field(min_length=8, max_length=48, pattern=r"^[A-Za-z0-9_-]+$")
    symbol: str = Field(pattern=r"^[A-Z][A-Z0-9.\-]{0,9}$")
    quantity: Decimal = Field(gt=Decimal(0))
    side: OrderSide
    submitted_from_signal_id: UUID | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class ExecutionOrder(BaseModel):
    """Broker acknowledgement and current order lifecycle state."""

    model_config = ConfigDict(frozen=True)

    order_id: UUID = Field(default_factory=uuid4)
    client_order_id: str
    broker_order_id: str | None = None
    symbol: str
    quantity: Decimal
    side: OrderSide
    status: OrderLifecycleStatus
    submitted_at: datetime | None = None
    filled_at: datetime | None = None
    filled_quantity: Decimal = Decimal(0)
    average_fill_price: Decimal | None = None
    reason: str | None = None


class ExecutionProvider(ABC):
    """Execution provider boundary kept separate from market-data ingestion."""

    @property
    @abstractmethod
    def is_paper(self) -> bool:
        """Return whether this provider is attached to a paper account."""

    @abstractmethod
    def configure_runtime(self, *, is_paper: bool, order_submission_enabled: bool) -> None:
        """Apply validated runtime controls without exposing credentials to callers."""

    @abstractmethod
    async def submit_market_order(self, request: OrderRequest) -> ExecutionOrder:
        """Submit an approved, idempotent market order and return broker state."""

    @abstractmethod
    async def get_account(self) -> AccountSnapshot:
        """Return current account capital and buying-power state."""

    @abstractmethod
    async def list_positions(self) -> tuple[PositionSnapshot, ...]:
        """Return current holdings used by portfolio risk controls."""

    @abstractmethod
    async def close_position(self, symbol: str, client_order_id: str) -> ExecutionOrder:
        """Close a broker position using an idempotency identifier."""
