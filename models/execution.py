"""Durable execution audit records for automated broker orders and account state."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class ExecutionOrderRecord(Base):
    """One idempotent order intent and its broker lifecycle, never reconstructed from logs."""

    __tablename__ = "execution_orders"
    __table_args__ = (
        Index("ix_execution_orders_symbol_created_at", "symbol", "created_at"),
        Index("ix_execution_orders_status", "status"),
    )

    order_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    client_order_id: Mapped[str] = mapped_column(String(48), unique=True)
    broker_order_id: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    symbol: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    side: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(32))
    strategy: Mapped[str | None] = mapped_column(String(128), nullable=True)
    signal_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    filled_quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    average_fill_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    reason: Mapped[str | None] = mapped_column(String(1_000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class AccountSnapshotRecord(Base):
    """Point-in-time account balance snapshot for P/L, capital, and incident analysis."""

    __tablename__ = "account_snapshots"
    __table_args__ = (Index("ix_account_snapshots_account_updated", "account_id", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64))
    cash: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    equity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    buying_power: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    previous_close_equity: Mapped[Decimal | None] = mapped_column(Numeric(20, 8), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class PositionSnapshotRecord(Base):
    """Point-in-time holdings snapshot used for historic portfolio/P&L reconstruction."""

    __tablename__ = "position_snapshots"
    __table_args__ = (Index("ix_position_snapshots_symbol_updated", "symbol", "updated_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[str] = mapped_column(String(64))
    symbol: Mapped[str] = mapped_column(String(10))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    average_entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    market_value: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    cost_basis: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    unrealized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    unrealized_pnl_percent: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
