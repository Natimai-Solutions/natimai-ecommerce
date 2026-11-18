"""Accueil : sélections de produits et catégories choisies

Revision ID: c7e8f9a0b1c2
Revises: b6d7e8f9a0b1
Create Date: 2026-11-19 04:30:00.000000

Les produits d'une sélection manuelle et les catégories choisies d'une
section, dans leur ordre (chantier accueil et messagerie, lot A2).
"""

import sqlalchemy as sa
from alembic import op

revision = "c7e8f9a0b1c2"
down_revision = "b6d7e8f9a0b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "homepage_block_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("block_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=True),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("label", sa.String(length=100), nullable=True),
        sa.ForeignKeyConstraint(
            ["block_id"], ["homepage_blocks.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["category_id"], ["categories.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_homepage_block_items_block_id", "homepage_block_items", ["block_id"]
    )


def downgrade() -> None:
    op.drop_table("homepage_block_items")
    op.execute("DELETE FROM homepage_blocks WHERE kind = 'collection'")
