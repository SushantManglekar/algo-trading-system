"""Create the persisted operator trading-control plane.

Revision ID: 20260731_0004
Revises: 20260725_0003
Create Date: 2026-07-31 01:00:00
"""

import sqlalchemy as sa

from alembic import op

revision = "20260731_0004"
down_revision = "20260725_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "trading_control",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("mode", sa.String(length=8), nullable=False),
        sa.Column("place_orders_automatically", sa.Boolean(), nullable=False),
        sa.Column("monitoring_enabled", sa.Boolean(), nullable=False),
        sa.Column("symbols", sa.JSON(), nullable=False),
        sa.Column("strategy", sa.JSON(), nullable=False),
        sa.Column("risk_policy", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "trading_control_audit",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("control_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("configuration", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["control_id"], ["trading_control.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_trading_control_audit_version", "trading_control_audit", ["version"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_trading_control_audit_version", table_name="trading_control_audit")
    op.drop_table("trading_control_audit")
    op.drop_table("trading_control")
