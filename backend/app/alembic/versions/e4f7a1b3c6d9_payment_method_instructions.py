"""moyens de paiement : instructions propres à chaque moyen

Revision ID: e4f7a1b3c6d9
Revises: d3e6f9a2b5c8
Create Date: 2026-09-30 14:00:00.000000

``payment_methods.instructions`` : texte envoyé au client pour ce moyen
(IBAN d'un compte précis, adresse d'un bureau…). Vide = les instructions de
son type (Paramètres système), puis le texte par défaut du fournisseur. Permet
deux virements vers deux banques différentes.
"""

import sqlalchemy as sa
from alembic import op

revision = "e4f7a1b3c6d9"
down_revision = "d3e6f9a2b5c8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_methods",
        sa.Column("instructions", sa.String(length=2000), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("payment_methods", "instructions")
