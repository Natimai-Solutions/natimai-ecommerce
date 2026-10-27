"""catégories parentes / enfants : categories.parent_id

Revision ID: b3d5f7a9c1e2
Revises: a9f1c3e5b7d2
Create Date: 2026-10-06 14:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b3d5f7a9c1e2"
down_revision = "a9f1c3e5b7d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every existing category stays a top-level one.
    op.add_column(
        "categories",
        sa.Column("parent_id", sa.Uuid(), nullable=True),
    )
    op.create_index("ix_categories_parent_id", "categories", ["parent_id"])
    op.create_foreign_key(
        "fk_categories_parent_id_categories",
        "categories",
        "categories",
        ["parent_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_categories_parent_id_categories", "categories", type_="foreignkey"
    )
    op.drop_index("ix_categories_parent_id", table_name="categories")
    op.drop_column("categories", "parent_id")
