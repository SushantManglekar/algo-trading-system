"""Durable runtime-control configuration and immutable audit records."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class TradingControlRecord(Base):
    """Singleton operator configuration applied by the runtime coordinator."""

    __tablename__ = "trading_control"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    mode: Mapped[str] = mapped_column(String(8))
    place_orders_automatically: Mapped[bool] = mapped_column(Boolean)
    monitoring_enabled: Mapped[bool] = mapped_column(Boolean)
    symbols: Mapped[list[str]] = mapped_column(JSON)
    strategy: Mapped[dict[str, object]] = mapped_column(JSON)
    risk_policy: Mapped[dict[str, object]] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TradingControlAuditRecord(Base):
    """Append-only history of runtime configuration versions."""

    __tablename__ = "trading_control_audit"
    __table_args__ = (Index("ix_trading_control_audit_version", "version"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    control_id: Mapped[int] = mapped_column(ForeignKey("trading_control.id"))
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration: Mapped[dict[str, object]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
