"""journal des prix : product_price_history

Revision ID: n5e2a8c3d9f1
Revises: m4d1f7b2c8e9
Create Date: 2026-09-26 22:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "n5e2a8c3d9f1"
down_revision = "m4d1f7b2c8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_price_history",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("old_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("new_price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("reason", sa.String(length=120), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "product_id", "reason", "created_at"):
        op.create_index(
            op.f(f"ix_product_price_history_{column}"),
            "product_price_history",
            [column],
        )


def downgrade() -> None:
    for column in ("created_at", "reason", "product_id", "id"):
        op.drop_index(
            op.f(f"ix_product_price_history_{column}"),
            table_name="product_price_history",
        )
    op.drop_table("product_price_history")
