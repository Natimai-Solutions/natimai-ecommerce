"""Retrait de la préférence « e-mails de commande et paiement »

Revision ID: c1d2e3f4a5b6
Revises: b9c0d1e2f3a4
Create Date: 2026-11-18 22:30:00.000000

`user_preferences.notification_email_enabled` n'était lu par aucun envoi :
l'interrupteur « Commande et paiement » de la vitrine ne coupait rien. Ces
e-mails (confirmation, paiement, facture) sont transactionnels et partent
toujours ; la colonne est retirée (chantier accueil et messagerie, §12.3).
"""

import sqlalchemy as sa
from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b9c0d1e2f3a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("user_preferences", "notification_email_enabled")


def downgrade() -> None:
    op.add_column(
        "user_preferences",
        sa.Column(
            "notification_email_enabled",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )
