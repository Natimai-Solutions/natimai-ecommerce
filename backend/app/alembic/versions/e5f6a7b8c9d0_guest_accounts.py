"""commande sans compte : comptes invités

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-10-27 15:00:00.000000

Un compte ouvert au paiement sans mot de passe est marqué « invité » jusqu'à
ce que la personne choisisse un mot de passe (lien reçu par e-mail) ou
s'inscrive avec la même adresse.
"""

import sqlalchemy as sa
from alembic import op

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("is_guest", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    op.drop_column("users", "is_guest")
