"""add_order_checkout_amount_snapshots

Revision ID: b7e2c9d1f4a8
Revises: c1a9f4d52e10
Create Date: 2026-05-09 10:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "b7e2c9d1f4a8"
down_revision = "c1a9f4d52e10"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column(
            "subtotal_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "shipping_fee_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "payment_fee_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "total_fees_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )

    op.alter_column("orders", "subtotal_amount", server_default=None)
    op.alter_column("orders", "shipping_fee_amount", server_default=None)
    op.alter_column("orders", "payment_fee_amount", server_default=None)
    op.alter_column("orders", "total_fees_amount", server_default=None)


def downgrade():
    op.drop_column("orders", "total_fees_amount")
    op.drop_column("orders", "payment_fee_amount")
    op.drop_column("orders", "shipping_fee_amount")
    op.drop_column("orders", "subtotal_amount")
