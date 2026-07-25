"""Durable tick persistence model."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class TickRecord(Base):
    __tablename__ = "ticks"
    __table_args__ = (Index("ix_ticks_symbol_timestamp", "symbol", "timestamp"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    symbol: Mapped[str] = mapped_column(String(10), index=True)
    exchange: Mapped[str] = mapped_column(String(32))
    price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    bid: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    ask: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    volume: Mapped[Decimal] = mapped_column(Numeric(22, 8))
    trade_size: Mapped[Decimal] = mapped_column(Numeric(22, 8))
    conditions: Mapped[list[str]] = mapped_column(JSON, default=list)
