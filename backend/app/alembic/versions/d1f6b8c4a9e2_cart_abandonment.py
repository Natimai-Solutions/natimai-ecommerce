"""relance des paniers abandonnés : activité du panier et opt-out marketing

Le panier n'avait aucun horodatage fiable (created_at / modify_at restaient
NULL : le CRUD panier ne passe pas par le CRUD générique). Deux colonnes
portent désormais ce que le balayage horaire lit : la dernière activité et
la date de la relance envoyée. Les préférences gagnent l'opt-out des e-mails
commerciaux, distinct des e-mails transactionnels.

Revision ID: d1f6b8c4a9e2
Revises: c9e5a3b7d2f4
Create Date: 2026-09-10 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d1f6b8c4a9e2"
down_revision = "c9e5a3b7d2f4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("carts", sa.Column("last_activity_at", sa.DateTime(), nullable=True))
    op.add_column(
        "carts", sa.Column("abandonment_reminded_at", sa.DateTime(), nullable=True)
    )
    op.create_index("ix_carts_last_activity_at", "carts", ["last_activity_at"])
    # Existing carts: the best stamp we have, else nothing (never reminded).
    op.execute(
        "UPDATE carts SET last_activity_at = COALESCE(modify_at, created_at) "
        "WHERE last_activity_at IS NULL"
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "marketing_email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "marketing_email_enabled")
    op.drop_index("ix_carts_last_activity_at", table_name="carts")
    op.drop_column("carts", "abandonment_reminded_at")
    op.drop_column("carts", "last_activity_at")
