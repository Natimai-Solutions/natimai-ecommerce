"""add sequential order_number to orders (M5)

Human-readable order reference ``CMD-{YYYY}-{NNNNN}`` backed by a dedicated
PostgreSQL sequence. Gaps are acceptable (a rolled-back checkout burns a
number) — this is a communication reference, not an accounting one. The
invoice number (M3) has its own gap-free counter.

Nullable: pre-existing orders keep no number (no retroactive backfill).

Revision ID: e4b1c7d9a250
Revises: a9c5e1f3b7d2
Create Date: 2026-08-25 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e4b1c7d9a250"
down_revision = "a9c5e1f3b7d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS order_number_seq START WITH 1")
    op.add_column(
        "orders",
        sa.Column("order_number", sa.String(length=32), nullable=True),
    )
    op.create_index(
        "ix_orders_order_number",
        "orders",
        ["order_number"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_orders_order_number", table_name="orders")
    op.drop_column("orders", "order_number")
    op.execute("DROP SEQUENCE IF EXISTS order_number_seq")
