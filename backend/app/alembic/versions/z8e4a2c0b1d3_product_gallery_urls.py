"""plusieurs images par produit : products.gallery_urls

Revision ID: z8e4a2c0b1d3
Revises: y7d3f1b9a0c2
Create Date: 2026-10-04 13:00:00.000000

``image_url`` reste l'image principale (cartes, panier, lignes de commande) ;
``gallery_urls`` porte les images supplémentaires, affichées à sa suite sur la
fiche produit, avant les photos Icecat.
"""

import sqlalchemy as sa
from alembic import op

revision = "z8e4a2c0b1d3"
down_revision = "y7d3f1b9a0c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("gallery_urls", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("products", "gallery_urls")
