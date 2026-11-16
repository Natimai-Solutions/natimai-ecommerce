"""destinataire, société et téléphone sur l'adresse

Revision ID: d0e1f2a3b4c5
Revises: c9d0e1f2a3b4
Create Date: 2026-11-16 22:00:00.000000

Le transporteur, le retrait et les livraisons dans les îles ont besoin du
nom du destinataire et d'un téléphone (audit fonctionnel, M8).
"""

import sqlalchemy as sa
from alembic import op

revision = "d0e1f2a3b4c5"
down_revision = "c9d0e1f2a3b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("addresses", sa.Column("recipient_name", sa.String(150), nullable=True))
    op.add_column("addresses", sa.Column("company", sa.String(150), nullable=True))
    op.add_column("addresses", sa.Column("phone", sa.String(40), nullable=True))


def downgrade() -> None:
    op.drop_column("addresses", "phone")
    op.drop_column("addresses", "company")
    op.drop_column("addresses", "recipient_name")
