"""add refunds table

Revision ID: e3f9a1c7b2d4
Revises: d2e7f5a4b9c3
Create Date: 2026-06-26 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e3f9a1c7b2d4"
down_revision = "d2e7f5a4b9c3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "refunds",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=50), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=True),
        sa.Column("status", sa.String(length=50), nullable=False),
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
        sa.Column("processed_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_refunds_payment_id"), "refunds", ["payment_id"], unique=False
    )
    op.create_index(op.f("ix_refunds_order_id"), "refunds", ["order_id"], unique=False)
    op.create_index(op.f("ix_refunds_status"), "refunds", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_refunds_status"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_order_id"), table_name="refunds")
    op.drop_index(op.f("ix_refunds_payment_id"), table_name="refunds")
    op.drop_table("refunds")
