"""Phase 2 – user_preferences table

Revision ID: b4c2d8e1f5a6
Revises: a3b1c7e2d9f5
Create Date: 2026-06-08 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "b4c2d8e1f5a6"
down_revision = "a3b1c7e2d9f5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_preferences",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("notification_email_enabled", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("notification_shipping_steps", sa.Boolean(), nullable=False, server_default="true"),
        sa.Column("default_shipping_preference", sa.String(length=50), nullable=True),
        sa.Column("locale", sa.String(length=10), nullable=True),
        sa.Column("currency_pref", sa.String(length=10), nullable=True),
        sa.Column("preferred_shipping_mode", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id"),
    )
    op.create_index("ix_user_preferences_id", "user_preferences", ["id"], unique=False)
    op.create_index("ix_user_preferences_user_id", "user_preferences", ["user_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_user_preferences_user_id", table_name="user_preferences")
    op.drop_index("ix_user_preferences_id", table_name="user_preferences")
    op.drop_table("user_preferences")
