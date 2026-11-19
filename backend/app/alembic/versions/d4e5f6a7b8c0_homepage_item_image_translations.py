"""Accueil : image et libellé traduit d'une catégorie choisie

Revision ID: d4e5f6a7b8c0
Revises: c3d4e5f6a7b9
Create Date: 2026-11-19 17:00:00.000000

Une catégorie choisie de l'accueil peut avoir une image propre et un libellé
dans chaque langue (R3 du chantier accueil et messagerie).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d4e5f6a7b8c0"
down_revision = "c3d4e5f6a7b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "homepage_block_items",
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default="{}",
            nullable=False,
        ),
    )
    op.add_column("homepage_block_items", sa.Column("media_id", sa.Uuid(), nullable=True))
    op.create_foreign_key(
        "homepage_block_items_media_id_fkey",
        "homepage_block_items",
        "media_assets",
        ["media_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "homepage_block_items_media_id_fkey", "homepage_block_items", type_="foreignkey"
    )
    op.drop_column("homepage_block_items", "media_id")
    op.drop_column("homepage_block_items", "translations")
