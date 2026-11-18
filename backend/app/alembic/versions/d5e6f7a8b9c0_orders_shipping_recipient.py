"""Destinataire et téléphone de livraison figés sur la commande

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-11-18 12:00:00.000000

L'adresse de la commande était un texte composé par la vitrine (destinataire
et téléphone compris), repris tel quel comme adresse de l'acheteur sur la
facture (relecture du 17/11/2026). Le serveur la construit désormais depuis
l'adresse enregistrée ; le destinataire et le téléphone ont leurs colonnes.
"""

import sqlalchemy as sa
from alembic import op

revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("shipping_recipient", sa.String(length=150), nullable=True)
    )
    op.add_column(
        "orders", sa.Column("shipping_phone", sa.String(length=40), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("orders", "shipping_phone")
    op.drop_column("orders", "shipping_recipient")
