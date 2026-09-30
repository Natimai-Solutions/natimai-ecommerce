"""fournisseurs : quantité et prix minimum à l'import fichier (R4 / S2)

Revision ID: d9e3f6a8b1c5
Revises: c8d2e5f7a9b4
Create Date: 2026-10-01 08:00:00.000000

``suppliers.min_quantity`` / ``suppliers.min_price`` : seuils propres à un
fournisseur, appliqués à l'import CSV / Excel (les réglages globaux
``SUPPLIER_SYNC_MIN_*`` ne valent que pour la synchro d'inventaire des API).
Vides pour les fournisseurs existants : rien ne change.
"""

import sqlalchemy as sa
from alembic import op

revision = "d9e3f6a8b1c5"
down_revision = "c8d2e5f7a9b4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "suppliers",
        sa.Column("min_quantity", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "suppliers",
        sa.Column("min_price", sa.Numeric(14, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("suppliers", "min_price")
    op.drop_column("suppliers", "min_quantity")
