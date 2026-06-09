"""add import-route fields to shipping_routes

Revision ID: a3b1c7e2d9f5
Revises: c5d9e2f1a8b4
Create Date: 2026-05-28 00:00:00.000000

Three new columns support the import-route / service-level mechanism:
  - service_level  : cross-corridor key (rapide/economique/ecologique)
  - customer_label : dropdown label shown to the customer
  - is_default_import : pre-selected route for anonymous users
"""

import sqlalchemy as sa
from alembic import op

revision = "a3b1c7e2d9f5"
down_revision = "c5d9e2f1a8b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipping_routes",
        sa.Column("service_level", sa.String(length=50), nullable=True),
    )
    op.add_column(
        "shipping_routes",
        sa.Column("customer_label", sa.String(length=100), nullable=True),
    )
    op.add_column(
        "shipping_routes",
        sa.Column("is_default_import", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.create_index(
        "ix_shipping_routes_service_level",
        "shipping_routes",
        ["service_level"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_shipping_routes_service_level", table_name="shipping_routes")
    op.drop_column("shipping_routes", "is_default_import")
    op.drop_column("shipping_routes", "customer_label")
    op.drop_column("shipping_routes", "service_level")
