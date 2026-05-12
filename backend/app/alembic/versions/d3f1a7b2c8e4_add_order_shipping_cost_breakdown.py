"""add_order_shipping_cost_breakdown

Revision ID: d3f1a7b2c8e4
Revises: b7e2c9d1f4a8
Create Date: 2026-05-11 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "d3f1a7b2c8e4"
down_revision = "b7e2c9d1f4a8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column("shipping_cost_breakdown", sa.JSON(), nullable=True),
    )


def downgrade():
    op.drop_column("orders", "shipping_cost_breakdown")
