"""moyens de paiement : acompte autorisé ou non (R3-P3)

Revision ID: b1c4d7e2f9a3
Revises: a7m3e9d1h5b2
Create Date: 2026-09-30 09:00:00.000000

``payment_methods.deposit_allowed`` : un moyen peut régler l'acompte d'une
commande (vrai par défaut, pour tous les moyens existants). L'admin l'éteint
pour exclure un moyen de l'acompte ; le solde reste payable par tout moyen.
"""

import sqlalchemy as sa
from alembic import op

revision = "b1c4d7e2f9a3"
down_revision = "a7m3e9d1h5b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_methods",
        sa.Column(
            "deposit_allowed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("payment_methods", "deposit_allowed")
