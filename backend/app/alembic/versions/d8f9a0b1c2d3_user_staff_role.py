"""Rôles d'équipe du back-office

Revision ID: d8f9a0b1c2d3
Revises: c7e8f9a0b1c2
Create Date: 2026-11-19 05:30:00.000000

Un membre de l'équipe qui n'est pas superuser reçoit un rôle (service client,
commercial) qui lui ouvre la messagerie de ses canaux, la lecture des
commandes et, pour le commercial, les demandes de devis (lot ROLE).
"""

import sqlalchemy as sa
from alembic import op

revision = "d8f9a0b1c2d3"
down_revision = "c7e8f9a0b1c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("staff_role", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "staff_role")
