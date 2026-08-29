"""customs rate resolved via category default (F1)

``products.customs_rate_pct`` devient nullable : NULL signifie « hérite du
défaut de la catégorie » (``categories.default_customs_rate_pct``, nouvelle
colonne). La sync fournisseur ne renseignant jamais ce taux, tous les produits
portaient le défaut 0,00 — soit une douane nulle silencieuse et un prix de
vente sous-évalué. Le backfill remet ces 0,00 jamais touchés à NULL pour que
la résolution par catégorie s'applique ; un produit dont le taux ne se résout
pas (ni produit, ni catégorie) n'est plus publiable côté vitrine.

Un 0,00 explicite reste possible (produit réellement exonéré) : il suffit de
le re-saisir via l'admin après cette migration.

Revision ID: a9c4e1f7b3d2
Revises: e5f9c3a7b2d8
Create Date: 2026-08-28 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a9c4e1f7b3d2"
down_revision = "e5f9c3a7b2d8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "categories",
        sa.Column(
            "default_customs_rate_pct",
            sa.Numeric(precision=8, scale=2),
            nullable=True,
        ),
    )
    op.alter_column(
        "products",
        "customs_rate_pct",
        existing_type=sa.Numeric(precision=8, scale=2),
        nullable=True,
        server_default=None,
    )
    # Backfill : les 0,00 sont le défaut jamais renseigné par la sync, pas une
    # exonération choisie — on les remet à NULL pour activer la résolution par
    # catégorie et le garde-fou de publication.
    op.execute("UPDATE products SET customs_rate_pct = NULL WHERE customs_rate_pct = 0")


def downgrade() -> None:
    op.execute("UPDATE products SET customs_rate_pct = 0 WHERE customs_rate_pct IS NULL")
    op.alter_column(
        "products",
        "customs_rate_pct",
        existing_type=sa.Numeric(precision=8, scale=2),
        nullable=False,
        server_default=sa.text("0"),
    )
    op.drop_column("categories", "default_customs_rate_pct")
