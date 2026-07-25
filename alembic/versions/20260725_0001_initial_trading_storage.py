"""Create durable market, signal, outcome, and manual-journal tables.

Revision ID: 20260725_0001
Revises:
Create Date: 2026-07-25 00:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260725_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ticks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("symbol", sa.String(length=10), nullable=False),
        sa.Column("exchange", sa.String(length=32), nullable=False),
        sa.Column("price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("bid", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("ask", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("volume", sa.Numeric(precision=22, scale=8), nullable=False),
        sa.Column("trade_size", sa.Numeric(precision=22, scale=8), nullable=False),
        sa.Column("conditions", sa.JSON(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_ticks_timestamp", "ticks", ["timestamp"], unique=False)
    op.create_index("ix_ticks_symbol", "ticks", ["symbol"], unique=False)
    op.create_index("ix_ticks_symbol_timestamp", "ticks", ["symbol", "timestamp"], unique=False)

    op.create_table(
        "candles",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=10), nullable=False),
        sa.Column("interval", sa.String(length=8), nullable=False),
        sa.Column("start_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("end_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("open", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("high", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("low", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("close", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("volume", sa.Numeric(precision=22, scale=8), nullable=False),
        sa.Column("is_complete", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("symbol", "interval", "start_at", name="uq_candles_series_start"),
    )
    op.create_index("ix_candles_series_end", "candles", ["symbol", "interval", "end_at"], unique=False)

    op.create_table(
        "signals",
        sa.Column("signal_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=10), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("strategy", sa.String(length=128), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("stop_loss", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("take_profit", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("atr_stop_loss", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("trailing_stop_distance", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("risk_reward", sa.Numeric(precision=8, scale=3), nullable=False),
        sa.Column("position_size", sa.Integer(), nullable=False),
        sa.Column("position_risk", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("expected_move", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("confidence", sa.Numeric(precision=4, scale=3), nullable=False),
        sa.Column("reason", sa.String(length=1000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("signal_id"),
    )
    op.create_index("ix_signals_symbol_timestamp", "signals", ["symbol", "timestamp"], unique=False)

    op.create_table(
        "signal_outcomes",
        sa.Column("outcome_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=10), nullable=False),
        sa.Column("direction", sa.String(length=8), nullable=False),
        sa.Column("signal_timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("signal_payload", sa.JSON(), nullable=False),
        sa.Column("exit_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("r_multiple", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("holding_seconds", sa.Numeric(precision=20, scale=3), nullable=False),
        sa.PrimaryKeyConstraint("outcome_id"),
    )
    op.create_index("ix_signal_outcomes_closed_at", "signal_outcomes", ["closed_at"], unique=False)

    op.create_table(
        "manual_trade_journal",
        sa.Column("trade_id", sa.Uuid(), nullable=False),
        sa.Column("symbol", sa.String(length=10), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=8), nullable=False),
        sa.Column("entry_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("entry_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("exit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("notes", sa.String(length=4000), nullable=True),
        sa.Column("tags", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("side IN ('BUY', 'SELL')", name="ck_manual_trade_side"),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_manual_trade_status"),
        sa.PrimaryKeyConstraint("trade_id"),
    )
    op.create_index(
        "ix_manual_trade_symbol_entry_at", "manual_trade_journal", ["symbol", "entry_at"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_manual_trade_symbol_entry_at", table_name="manual_trade_journal")
    op.drop_table("manual_trade_journal")
    op.drop_index("ix_signal_outcomes_closed_at", table_name="signal_outcomes")
    op.drop_table("signal_outcomes")
    op.drop_index("ix_signals_symbol_timestamp", table_name="signals")
    op.drop_table("signals")
    op.drop_index("ix_candles_series_end", table_name="candles")
    op.drop_table("candles")
    op.drop_index("ix_ticks_symbol_timestamp", table_name="ticks")
    op.drop_index("ix_ticks_symbol", table_name="ticks")
    op.drop_index("ix_ticks_timestamp", table_name="ticks")
    op.drop_table("ticks")
