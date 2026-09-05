"""weight bands and franco on shipping routes

Revision ID: f3c8d5e2b7a4
Revises: e2b7c4d9a1f3
Create Date: 2026-09-05 00:00:00.000000

Classic carrier tariffs (Colissimo, Chronopost, DHL…) are grids by weight
band plus a "free from X" threshold, not a linear per-kg rate:
  - weight_bands : JSON [{max_kg, price}] replacing price_per_kg × weight
  - free_shipping_threshold : declared value from which the route is free
Both nullable; null keeps the existing base_price + price_per_kg tariff.
"""

import sqlalchemy as sa
from alembic import op

revision = "f3c8d5e2b7a4"
down_revision = "e2b7c4d9a1f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipping_routes",
        sa.Column("weight_bands", sa.JSON(), nullable=True),
    )
    op.add_column(
        "shipping_routes",
        sa.Column(
            "free_shipping_threshold", sa.Numeric(precision=12, scale=2), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("shipping_routes", "free_shipping_threshold")
    op.drop_column("shipping_routes", "weight_bands")
