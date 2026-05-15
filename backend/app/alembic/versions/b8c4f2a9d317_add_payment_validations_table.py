"""add payment_validations table

Revision ID: b8c4f2a9d317
Revises: a6b3d4e5f901
Create Date: 2026-05-15 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b8c4f2a9d317"
down_revision = "a6b3d4e5f901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_validations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("admin_user_id", sa.Uuid(), nullable=True),
        sa.Column("reason", sa.String(length=1024), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_admin_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["admin_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_validations_id"),
        "payment_validations",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_validations_payment_id"),
        "payment_validations",
        ["payment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_validations_action"),
        "payment_validations",
        ["action"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_validations_admin_user_id"),
        "payment_validations",
        ["admin_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_payment_validations_admin_user_id"),
        table_name="payment_validations",
    )
    op.drop_index(
        op.f("ix_payment_validations_action"),
        table_name="payment_validations",
    )
    op.drop_index(
        op.f("ix_payment_validations_payment_id"),
        table_name="payment_validations",
    )
    op.drop_index(
        op.f("ix_payment_validations_id"),
        table_name="payment_validations",
    )
    op.drop_table("payment_validations")
