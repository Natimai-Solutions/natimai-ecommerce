"""promotions : codes promo non cumulables avec les articles en promotion

Revision ID: c8d2e5f7a9b4
Revises: b7c1d4e6f9a3
Create Date: 2026-09-30 21:00:00.000000

``discounts.applies_to_promoted`` : un code promo peut exclure les articles
concernés par une promotion en cours (vrai pour les codes existants : rien
ne change). Les promotions elles-mêmes sont des lignes ``discounts`` de type
« promotion » (déjà présentes dans le modèle) : le client paie le meilleur
prix entre celui de son groupe et le prix promotionnel.
"""

import sqlalchemy as sa
from alembic import op

revision = "c8d2e5f7a9b4"
down_revision = "b7c1d4e6f9a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "discounts",
        sa.Column(
            "applies_to_promoted",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("discounts", "applies_to_promoted")
