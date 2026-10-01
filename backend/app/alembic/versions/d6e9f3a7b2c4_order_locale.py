"""commandes : langue du client (R7)

Revision ID: d6e9f3a7b2c4
Revises: c5d8e2f6a1b3
Create Date: 2026-10-01 22:00:00.000000

``orders.locale`` : la langue de l'interface au checkout (fr, en…). Les
e-mails et documents de la commande la suivent. Nulle sur les commandes
antérieures : la langue par défaut de la boutique s'applique.
"""

import sqlalchemy as sa
from alembic import op

revision = "d6e9f3a7b2c4"
down_revision = "c5d8e2f6a1b3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("orders", sa.Column("locale", sa.String(length=8), nullable=True))


def downgrade() -> None:
    op.drop_column("orders", "locale")
