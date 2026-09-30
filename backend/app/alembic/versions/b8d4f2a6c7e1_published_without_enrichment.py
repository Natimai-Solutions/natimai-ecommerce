"""publication d'un article sans attendre l'enrichissement Icecat

La vitrine n'affichait un article synchronisé qu'une fois enrichi par Icecat
(``is_enriched``). Un article importé par fichier qu'Icecat ne reconnaît pas
(consommable sans code-barres, marque locale) restait donc caché pour
toujours, sans recours dans l'admin.

``products.published_without_enrichment`` porte la décision de l'admin (ou de
l'import fichier, sur option) de publier l'article tel quel ; Icecat peut
toujours l'enrichir plus tard, le drapeau n'y change rien.

Revision ID: b8d4f2a6c7e1
Revises: a7c3e9f1b2d4
Create Date: 2026-09-10 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b8d4f2a6c7e1"
down_revision = "a7c3e9f1b2d4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "published_without_enrichment",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "published_without_enrichment")
