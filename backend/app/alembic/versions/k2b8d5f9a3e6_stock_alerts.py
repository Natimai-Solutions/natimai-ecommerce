"""alerte « me prévenir » sur un produit indisponible

Revision ID: k2b8d5f9a3e6
Revises: j1a7c4e8b2d5
Create Date: 2026-09-26 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "k2b8d5f9a3e6"
down_revision = "j1a7c4e8b2d5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "stock_alerts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("notified_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "product_id", "user_id", "email", "status"):
        op.create_index(op.f(f"ix_stock_alerts_{column}"), "stock_alerts", [column])


def downgrade() -> None:
    for column in ("status", "email", "user_id", "product_id", "id"):
        op.drop_index(op.f(f"ix_stock_alerts_{column}"), table_name="stock_alerts")
    op.drop_table("stock_alerts")
