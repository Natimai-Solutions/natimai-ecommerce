"""le compte a-t-il un mot de passe choisi

Revision ID: e1f2a3b4c5d6
Revises: d0e1f2a3b4c5
Create Date: 2026-11-16 23:00:00.000000

Un compte lié à Google / Microsoft qui a aussi un vrai mot de passe se
supprimait sur la foi d'une connexion récente. La colonne dit si le titulaire
a choisi un mot de passe ; inconnue (NULL) pour les comptes existants, qui
gardent la règle d'avant.
"""

import sqlalchemy as sa
from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d0e1f2a3b4c5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("has_password", sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column("users", "has_password")
