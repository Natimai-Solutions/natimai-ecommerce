"""Adresse de facturation distincte : identifiant d'entreprise, bloc figé

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-11-18 15:00:00.000000

Une société qui paie des marchandises livrées ailleurs était facturée au nom
du compte, à l'adresse de livraison (décision du 18/11/2026). L'adresse porte
un identifiant (n° TAHITI, SIRET…) ; la commande fige le bloc facturé.
"""

import sqlalchemy as sa
from alembic import op

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("addresses", sa.Column("tax_id", sa.String(length=40), nullable=True))
    op.add_column(
        "orders", sa.Column("billing_name", sa.String(length=150), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("billing_address", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("billing_tax_id", sa.String(length=40), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("orders", "billing_tax_id")
    op.drop_column("orders", "billing_address")
    op.drop_column("orders", "billing_name")
    op.drop_column("addresses", "tax_id")
