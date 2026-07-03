"""add supplier_place_id to products

Revision ID: b5c9e2a7f1d3
Revises: a3b8d1f6c4e2
Create Date: 2026-06-29 17:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b5c9e2a7f1d3"
down_revision = "a3b8d1f6c4e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("supplier_place_id", sa.Uuid(), nullable=True),
    )
    op.create_index(
        op.f("ix_products_supplier_place_id"),
        "products",
        ["supplier_place_id"],
        unique=False,
    )
    op.create_foreign_key(
        "fk_products_supplier_place_id",
        "products",
        "places",
        ["supplier_place_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_products_supplier_place_id", "products", type_="foreignkey"
    )
    op.drop_index(op.f("ix_products_supplier_place_id"), table_name="products")
    op.drop_column("products", "supplier_place_id")
