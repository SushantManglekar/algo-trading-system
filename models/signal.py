"""Durable risk-managed signal persistence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class SignalRecord(Base):
    """Immutable approved signal proposal. It is explicitly not a broker order."""

    __tablename__ = "signals"
    __table_args__ = (Index("ix_signals_symbol_timestamp", "symbol", "timestamp"),)

    signal_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    symbol: Mapped[str] = mapped_column(String(10))
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    strategy: Mapped[str] = mapped_column(String(128))
    direction: Mapped[str] = mapped_column(String(8))
    entry_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    stop_loss: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    take_profit: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    atr_stop_loss: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    trailing_stop_distance: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    risk_reward: Mapped[Decimal] = mapped_column(Numeric(8, 3))
    position_size: Mapped[int] = mapped_column()
    position_risk: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    expected_move: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    confidence: Mapped[Decimal] = mapped_column(Numeric(4, 3))
    reason: Mapped[str] = mapped_column(String(1_000))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
