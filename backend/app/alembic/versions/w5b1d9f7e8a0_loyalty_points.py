"""points de fidélité (R8 / confort) : table loyalty_entries

Revision ID: w5b1d9f7e8a0
Revises: v4a0c8e6d7f9
Create Date: 2026-10-03 14:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "w5b1d9f7e8a0"
down_revision = "v4a0c8e6d7f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "loyalty_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("store_credit_entry_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["store_credit_entry_id"], ["store_credit_entries.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "user_id", "order_id"):
        op.create_index(f"ix_loyalty_entries_{column}", "loyalty_entries", [column])


def downgrade() -> None:
    for column in ("order_id", "user_id", "id"):
        op.drop_index(f"ix_loyalty_entries_{column}", table_name="loyalty_entries")
    op.drop_table("loyalty_entries")
