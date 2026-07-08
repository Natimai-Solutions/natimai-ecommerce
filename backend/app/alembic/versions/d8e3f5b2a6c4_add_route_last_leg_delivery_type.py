"""add last_leg_delivery_type to shipping_routes

Revision ID: d8e3f5b2a6c4
Revises: c7d2f4a9e5b1
Create Date: 2026-07-02 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d8e3f5b2a6c4"
down_revision = "c7d2f4a9e5b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipping_routes",
        sa.Column("last_leg_delivery_type", sa.String(length=50), nullable=True),
    )
    op.create_index(
        op.f("ix_shipping_routes_last_leg_delivery_type"),
        "shipping_routes",
        ["last_leg_delivery_type"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_shipping_routes_last_leg_delivery_type"),
        table_name="shipping_routes",
    )
    op.drop_column("shipping_routes", "last_leg_delivery_type")
