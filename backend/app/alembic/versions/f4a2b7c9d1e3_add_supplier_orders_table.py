"""add supplier_orders table

Revision ID: f4a2b7c9d1e3
Revises: 8c2f1d4a6e90
Create Date: 2026-05-18 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "f4a2b7c9d1e3"
down_revision = "8c2f1d4a6e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "supplier_orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("supplier_name", sa.String(), nullable=False),
        sa.Column("local_order_id", sa.Uuid(), nullable=False),
        sa.Column("customer_order_number", sa.String(), nullable=False),
        sa.Column("supplier_order_number", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("supplier_status_label", sa.String(), nullable=True),
        sa.Column("lines_snapshot", sa.JSON(), nullable=True),
        sa.Column("supplier_response", sa.JSON(), nullable=True),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["local_order_id"], ["orders.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_supplier_orders_id"), "supplier_orders", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_supplier_orders_supplier_name"),
        "supplier_orders",
        ["supplier_name"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_orders_local_order_id"),
        "supplier_orders",
        ["local_order_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_orders_customer_order_number"),
        "supplier_orders",
        ["customer_order_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_orders_supplier_order_number"),
        "supplier_orders",
        ["supplier_order_number"],
        unique=False,
    )
    op.create_index(
        op.f("ix_supplier_orders_status"), "supplier_orders", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_supplier_orders_status"), table_name="supplier_orders")
    op.drop_index(
        op.f("ix_supplier_orders_supplier_order_number"), table_name="supplier_orders"
    )
    op.drop_index(
        op.f("ix_supplier_orders_customer_order_number"), table_name="supplier_orders"
    )
    op.drop_index(
        op.f("ix_supplier_orders_local_order_id"), table_name="supplier_orders"
    )
    op.drop_index(
        op.f("ix_supplier_orders_supplier_name"), table_name="supplier_orders"
    )
    op.drop_index(op.f("ix_supplier_orders_id"), table_name="supplier_orders")
    op.drop_table("supplier_orders")
