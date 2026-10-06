"""caractéristiques rattachées aux catégories boutique : spec_definitions.category_ids

Revision ID: x6c2e0a8f9b1
Revises: w5b1d9f7e8a0
Create Date: 2026-10-04 12:00:00.000000

Une définition de caractéristique s'applique désormais à des catégories de la
boutique choisies dans l'admin (``category_ids``, identifiants), en plus des
mots-clés de catégorie fournisseur (``categories``) qui restent utiles pour
Ingram / Icecat. Sans l'un ni l'autre, elle s'applique partout (inchangé).
"""

import sqlalchemy as sa
from alembic import op

revision = "x6c2e0a8f9b1"
down_revision = "w5b1d9f7e8a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "spec_definitions",
        sa.Column("category_ids", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("spec_definitions", "category_ids")
