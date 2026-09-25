"""pages éditables (comment ça marche, CGV…)

Revision ID: e5b3d7a9c4f1
Revises: d4a8c1e7f2b9
Create Date: 2026-09-25 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "e5b3d7a9c4f1"
down_revision = "d4a8c1e7f2b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "content_pages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("body_html", sa.Text(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_content_pages_id"), "content_pages", ["id"])
    op.create_index(op.f("ix_content_pages_slug"), "content_pages", ["slug"], unique=True)
    op.create_index(
        op.f("ix_content_pages_is_published"), "content_pages", ["is_published"]
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_content_pages_is_published"), table_name="content_pages")
    op.drop_index(op.f("ix_content_pages_slug"), table_name="content_pages")
    op.drop_index(op.f("ix_content_pages_id"), table_name="content_pages")
    op.drop_table("content_pages")
