"""fournisseurs : identifiants chiffrés des flux fichier (R4 / S3)

Revision ID: a3b6c9d2e4f8
Revises: f2a5b8c1d3e7
Create Date: 2026-10-01 14:00:00.000000

``suppliers.credentials_encrypted`` : identifiants du portail d'un
fournisseur dont le catalogue se télécharge par lien (Foxway, Picata…),
chiffrés par ``SUPPLIER_SECRETS_KEY`` (Fernet). Vide pour l'existant.
"""

import sqlalchemy as sa
from alembic import op

revision = "a3b6c9d2e4f8"
down_revision = "f2a5b8c1d3e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "suppliers", sa.Column("credentials_encrypted", sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("suppliers", "credentials_encrypted")
