"""Accueil : annonce, réassurance, bande de marques, bloc libre

Revision ID: a1b2c3d4e5f7
Revises: f0a1b2c3d4e5
Create Date: 2026-11-19 11:00:00.000000

Texte riche d'un bloc de contenu libre (``homepage_blocks.body_html``) et
marques choisies d'une bande de marques (``homepage_block_items.brand_id``),
lot A3. L'annonce et la réassurance n'ajoutent que des types de section.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f7"
down_revision = "f0a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("homepage_blocks", sa.Column("body_html", sa.Text(), nullable=True))
    op.add_column(
        "homepage_block_items", sa.Column("brand_id", sa.Uuid(), nullable=True)
    )
    op.create_foreign_key(
        "homepage_block_items_brand_id_fkey",
        "homepage_block_items",
        "brands",
        ["brand_id"],
        ["id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM homepage_blocks WHERE kind IN "
        "('announcement', 'reassurance', 'brand_strip', 'rich_text')"
    )
    op.drop_constraint(
        "homepage_block_items_brand_id_fkey", "homepage_block_items", type_="foreignkey"
    )
    op.drop_column("homepage_block_items", "brand_id")
    op.drop_column("homepage_blocks", "body_html")
