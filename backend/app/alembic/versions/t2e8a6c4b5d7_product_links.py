"""articles liés et suggestions (R9 / T7) : product_links, category_links

Revision ID: t2e8a6c4b5d7
Revises: s1d7f5b3a4c6
Create Date: 2026-10-02 06:00:00.000000
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "t2e8a6c4b5d7"
down_revision = "s1d7f5b3a4c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "product_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("linked_product_id", sa.Uuid(), nullable=False),
        sa.Column(
            "kind", sqlmodel.sql.sqltypes.AutoString(length=16), nullable=False
        ),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["linked_product_id"], ["products.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id", "linked_product_id", "kind", name="uq_product_links_pair"
        ),
    )
    op.create_index(op.f("ix_product_links_id"), "product_links", ["id"])
    op.create_index(op.f("ix_product_links_kind"), "product_links", ["kind"])
    op.create_index(
        op.f("ix_product_links_linked_product_id"), "product_links", ["linked_product_id"]
    )
    op.create_index(op.f("ix_product_links_product_id"), "product_links", ["product_id"])

    op.create_table(
        "category_links",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=False),
        sa.Column("suggested_category_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["suggested_category_id"], ["categories.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "category_id", "suggested_category_id", name="uq_category_links_pair"
        ),
    )
    op.create_index(op.f("ix_category_links_id"), "category_links", ["id"])
    op.create_index(
        op.f("ix_category_links_category_id"), "category_links", ["category_id"]
    )
    op.create_index(
        op.f("ix_category_links_suggested_category_id"),
        "category_links",
        ["suggested_category_id"],
    )


def downgrade() -> None:
    op.drop_table("category_links")
    op.drop_table("product_links")
