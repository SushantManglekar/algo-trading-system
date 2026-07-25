"""Manual trading journal persistence model; it never represents a broker order."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class ManualTradeRecord(Base):
    """User-entered trade journal record for audit and analytics reconciliation."""

    __tablename__ = "manual_trade_journal"
    __table_args__ = (
        CheckConstraint("side IN ('BUY', 'SELL')", name="ck_manual_trade_side"),
        CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_manual_trade_status"),
        Index("ix_manual_trade_symbol_entry_at", "symbol", "entry_at"),
    )

    trade_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String(10))
    side: Mapped[str] = mapped_column(String(4))
    status: Mapped[str] = mapped_column(String(8))
    entry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    quantity: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    exit_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_price: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    notes: Mapped[str | None] = mapped_column(String(4_000), nullable=True)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
