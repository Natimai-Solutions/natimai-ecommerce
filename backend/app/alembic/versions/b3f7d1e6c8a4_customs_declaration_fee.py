"""per-declaration customs fees on the customs place (F3)

Les redevances et participations dues à la douane sont facturées **par
déclaration**, pas par article : les répartir au prorata des lignes rend le
prix unitaire faux dans les deux sens selon la taille du panier. Elles sont
donc portées par le lieu de dédouanement (``places.customs_declaration_fee``)
et facturées une fois par expédition, comme le forfait d'un tronçon.

Le champ est nullable et vaut « non renseigné » : tant qu'aucun montant n'est
saisi, rien n'est facturé et le comportement est inchangé.

Revision ID: b3f7d1e6c8a4
Revises: a9c4e1f7b3d2
Create Date: 2026-08-31 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "b3f7d1e6c8a4"
down_revision = "a9c4e1f7b3d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column(
            "customs_declaration_fee",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("places", "customs_declaration_fee")
