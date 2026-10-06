"""devises acceptées par moyen de paiement : payment_methods.currencies

Revision ID: y7d3f1b9a0c2
Revises: x6c2e0a8f9b1
Create Date: 2026-10-04 12:30:00.000000

Un moyen de paiement liste les devises dans lesquelles il peut encaisser (vide =
toutes). Le client dont la devise d'affichage n'en fait pas partie est prévenu
au checkout que le paiement sera effectué dans une autre devise, avec le
montant converti.
"""

import sqlalchemy as sa
from alembic import op

revision = "y7d3f1b9a0c2"
down_revision = "x6c2e0a8f9b1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payment_methods",
        sa.Column("currencies", sa.JSON(), nullable=False, server_default="[]"),
    )


def downgrade() -> None:
    op.drop_column("payment_methods", "currencies")
