"""Create durable account, position, and automated-order audit storage.

Revision ID: 20260725_0002
Revises: 20260725_0001
Create Date: 2026-07-25 01:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260725_0002"
down_revision = "20260725_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "execution_orders",
        sa.Column("order_id", sa.Uuid(), nullable=False),
        sa.Column("client_order_id", sa.String(length=48), nullable=False),
        sa.Column("broker_order_id", sa.String(length=64), nullable=True),
        sa.Column("symbol", sa.String(length=10), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("side", sa.String(length=4), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("strategy", sa.String(length=128), nullable=True),
        sa.Column("signal_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("filled_quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("average_fill_price", sa.Numeric(precision=18, scale=8), nullable=True),
        sa.Column("reason", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("order_id"),
        sa.UniqueConstraint("broker_order_id"),
        sa.UniqueConstraint("client_order_id"),
    )
    op.create_index("ix_execution_orders_status", "execution_orders", ["status"], unique=False)
    op.create_index("ix_execution_orders_symbol_created_at", "execution_orders", ["symbol", "created_at"], unique=False)

    op.create_table(
        "account_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("cash", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("equity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("buying_power", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("previous_close_equity", sa.Numeric(precision=20, scale=8), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_account_snapshots_account_updated", "account_snapshots", ["account_id", "updated_at"], unique=False)

    op.create_table(
        "position_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=10), nullable=False),
        sa.Column("quantity", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(precision=18, scale=8), nullable=False),
        sa.Column("market_value", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("cost_basis", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("unrealized_pnl", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("unrealized_pnl_percent", sa.Numeric(precision=20, scale=8), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_position_snapshots_symbol_updated", "position_snapshots", ["symbol", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_position_snapshots_symbol_updated", table_name="position_snapshots")
    op.drop_table("position_snapshots")
    op.drop_index("ix_account_snapshots_account_updated", table_name="account_snapshots")
    op.drop_table("account_snapshots")
    op.drop_index("ix_execution_orders_symbol_created_at", table_name="execution_orders")
    op.drop_index("ix_execution_orders_status", table_name="execution_orders")
    op.drop_table("execution_orders")
