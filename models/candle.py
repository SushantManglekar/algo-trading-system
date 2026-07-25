"""Durable OHLCV candle persistence model."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class CandleRecord(Base):
    """One mutable candle state, unique at its series and opening instant."""

    __tablename__ = "candles"
    __table_args__ = (
        UniqueConstraint("symbol", "interval", "start_at", name="uq_candles_series_start"),
        Index("ix_candles_series_end", "symbol", "interval", "end_at"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    symbol: Mapped[str] = mapped_column(String(10))
    interval: Mapped[str] = mapped_column(String(8))
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    end_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    open: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    high: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    low: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    close: Mapped[Decimal] = mapped_column(Numeric(18, 8))
    volume: Mapped[Decimal] = mapped_column(Numeric(22, 8))
    is_complete: Mapped[bool] = mapped_column(Boolean)
