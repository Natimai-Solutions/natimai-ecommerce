"""chaîne d'intégrité des factures et des avoirs

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-11-04 10:00:00.000000

Chaque facture et chaque avoir porte l'empreinte du document précédent de sa
série et de son exercice, et la sienne (app/features/invoice/services/
integrity.py). Les documents déjà émis restent sans empreinte : la prochaine
émission de leur série et de leur exercice les scelle, dans l'ordre des
numéros.
"""

import sqlalchemy as sa
from alembic import op

revision = "f6a7b8c9d0e1"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None

_TABLES = ("invoices", "credit_notes")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(table, sa.Column("previous_hash", sa.String(64), nullable=True))
        op.add_column(table, sa.Column("chain_hash", sa.String(64), nullable=True))


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "chain_hash")
        op.drop_column(table, "previous_hash")
