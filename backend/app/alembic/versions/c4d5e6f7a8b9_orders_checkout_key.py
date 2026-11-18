"""Clé d'idempotence du checkout sur la commande

Revision ID: c4d5e6f7a8b9
Revises: f2a3b4c5d6e7
Create Date: 2026-11-18 10:00:00.000000

Le verrou du panier ne couvrait que les requêtes simultanées : un nouvel essai
après un délai dépassé reconstruisait un panier et créait une seconde
commande (D5, relecture du 17/11/2026). La vitrine envoie une clé par
soumission ; une commande existante pour (client, clé) est renvoyée.
"""

import sqlalchemy as sa
from alembic import op

revision = "c4d5e6f7a8b9"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders", sa.Column("checkout_key", sa.String(length=64), nullable=True)
    )
    op.create_index(
        "uq_orders_user_checkout_key",
        "orders",
        ["user_id", "checkout_key"],
        unique=True,
        postgresql_where=sa.text("checkout_key IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_orders_user_checkout_key", table_name="orders")
    op.drop_column("orders", "checkout_key")
