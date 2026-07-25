"""Immutable realized analytics outcome persistence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import JSON, DateTime, Index, Numeric, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class SignalOutcomeRecord(Base):
    """Observed close with an immutable signal snapshot for reproducible analytics."""

    __tablename__ = "signal_outcomes"
    __table_args__ = (Index("ix_signal_outcomes_closed_at", "closed_at"),)

    outcome_id: Mapped[UUID] = mapped_column(Uuid, primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10))
    direction: Mapped[str] = mapped_column(String(8))
    signal_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    signal_payload: Mapped[dict[str, object]] = mapped_column(JSON)
    exit_price: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    realized_pnl: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    r_multiple: Mapped[Decimal] = mapped_column(Numeric(20, 8))
    holding_seconds: Mapped[Decimal] = mapped_column(Numeric(20, 3))
