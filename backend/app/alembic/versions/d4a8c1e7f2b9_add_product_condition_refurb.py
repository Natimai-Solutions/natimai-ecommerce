"""état du produit (neuf / reconditionné) et détails du reconditionné

Revision ID: d4a8c1e7f2b9
Revises: c2f7a9d4e6b1
Create Date: 2026-09-25 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d4a8c1e7f2b9"
down_revision = "c2f7a9d4e6b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing product is new goods.
    op.add_column(
        "products",
        sa.Column(
            "condition",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'new'"),
        ),
    )
    op.create_index("ix_products_condition", "products", ["condition"])
    op.add_column(
        "products", sa.Column("condition_grade", sa.String(length=5), nullable=True)
    )
    op.add_column(
        "products", sa.Column("battery_health_pct", sa.Integer(), nullable=True)
    )
    op.add_column(
        "products", sa.Column("os_licence", sa.String(length=100), nullable=True)
    )
    op.add_column("products", sa.Column("warranty_months", sa.Integer(), nullable=True))


def downgrade() -> None:
    for column in ("warranty_months", "os_licence", "battery_health_pct", "condition_grade"):
        op.drop_column("products", column)
    op.drop_index("ix_products_condition", table_name="products")
    op.drop_column("products", "condition")
