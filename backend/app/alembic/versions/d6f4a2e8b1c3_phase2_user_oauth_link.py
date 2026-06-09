"""phase2_user_oauth_link

Revision ID: d6f4a2e8b1c3
Revises: c5e3f9a2b7d1
Create Date: 2026-06-08

Creates the user_oauth_links table for social login (Google, Microsoft).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d6f4a2e8b1c3"
down_revision: str | None = "c5e3f9a2b7d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "user_oauth_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("provider_user_id", sa.String(length=255), nullable=False),
        sa.Column("email_at_link", sa.String(length=255), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name="fk_oauth_links_user_id",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider", "provider_user_id", name="uq_oauth_provider_uid"
        ),
    )
    op.create_index("ix_user_oauth_links_id", "user_oauth_links", ["id"])
    op.create_index("ix_user_oauth_links_user_id", "user_oauth_links", ["user_id"])
    op.create_index("ix_user_oauth_links_provider", "user_oauth_links", ["provider"])


def downgrade() -> None:
    op.drop_index("ix_user_oauth_links_provider", "user_oauth_links")
    op.drop_index("ix_user_oauth_links_user_id", "user_oauth_links")
    op.drop_index("ix_user_oauth_links_id", "user_oauth_links")
    op.drop_table("user_oauth_links")
