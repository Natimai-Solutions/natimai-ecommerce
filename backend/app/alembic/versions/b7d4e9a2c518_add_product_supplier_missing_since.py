"""add products.supplier_missing_since for delisting

A SKU pulled from the supplier catalog used to stay active forever with its
last known price and stock: nothing ever noticed that Ingram had stopped
returning it. This column records the first price & availability response in
which the SKU went missing; the sync clears it as soon as the SKU reappears,
and deactivates the product once the gap exceeds the delisting grace period.

A timestamp rather than a boolean on purpose — a one-off supplier glitch must
not delist the catalog, only a persistent absence should.

Revision ID: b7d4e9a2c518
Revises: a9c4e1f7b3d2
Create Date: 2026-09-02 10:15:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b7d4e9a2c518"
down_revision = "a9c4e1f7b3d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("supplier_missing_since", sa.DateTime(), nullable=True),
    )
    op.create_index(
        "ix_products_supplier_missing_since",
        "products",
        ["supplier_missing_since"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_products_supplier_missing_since", table_name="products")
    op.drop_column("products", "supplier_missing_since")
