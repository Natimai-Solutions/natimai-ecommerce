"""jeton de sécurité par utilisateur : users.security_stamp

Revision ID: a1b2c3d4e5f6
Revises: b3d5f7a9c1e2
Create Date: 2026-10-25 09:00:00.000000

Chaque jeton d'accès porte le ``security_stamp`` de son utilisateur ; le
changer (mot de passe, désactivation, réinitialisation de la double
authentification) ferme aussitôt toutes les sessions. Les lignes existantes
reçoivent chacune une valeur aléatoire : les jetons d'accès déjà émis, sans
tampon, sont refusés une fois et renouvelés par le refresh token.
"""

import sqlalchemy as sa
from alembic import op

revision = "a1b2c3d4e5f6"
down_revision = "b3d5f7a9c1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column(
            "security_stamp",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("md5(random()::text)"),
        ),
    )


def downgrade() -> None:
    op.drop_column("users", "security_stamp")
