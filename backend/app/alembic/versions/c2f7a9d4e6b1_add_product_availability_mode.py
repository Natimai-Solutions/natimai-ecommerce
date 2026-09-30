"""mode de disponibilité des produits (stock / sur commande / continu)

Revision ID: c2f7a9d4e6b1
Revises: b9e4d2c7a1f5
Create Date: 2026-09-25 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c2f7a9d4e6b1"
down_revision = "b9e4d2c7a1f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing product keeps the historical behaviour ('stock').
    op.add_column(
        "products",
        sa.Column(
            "availability_mode",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'stock'"),
        ),
    )
    op.create_index(
        "ix_products_availability_mode", "products", ["availability_mode"]
    )


def downgrade() -> None:
    op.drop_index("ix_products_availability_mode", table_name="products")
    op.drop_column("products", "availability_mode")
