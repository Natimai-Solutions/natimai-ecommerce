"""avoir-crédit client : grand livre des octrois et utilisations

Revision ID: j1a7c4e8b2d5
Revises: i9f5b3d7e1a2
Create Date: 2026-09-26 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "j1a7c4e8b2d5"
down_revision = "i9f5b3d7e1a2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "store_credit_entries",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("id", "user_id", "order_id"):
        op.create_index(
            op.f(f"ix_store_credit_entries_{column}"), "store_credit_entries", [column]
        )


def downgrade() -> None:
    for column in ("order_id", "user_id", "id"):
        op.drop_index(
            op.f(f"ix_store_credit_entries_{column}"), table_name="store_credit_entries"
        )
    op.drop_table("store_credit_entries")
