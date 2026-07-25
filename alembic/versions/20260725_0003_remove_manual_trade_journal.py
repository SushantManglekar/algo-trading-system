"""Remove the obsolete manual trade journal.

Revision ID: 20260725_0003
Revises: 20260725_0002
Create Date: 2026-07-25 02:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260725_0003"
down_revision = "20260725_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_manual_trade_symbol_entry_at", table_name="manual_trade_journal")
    op.drop_table("manual_trade_journal")


def downgrade() -> None:
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
