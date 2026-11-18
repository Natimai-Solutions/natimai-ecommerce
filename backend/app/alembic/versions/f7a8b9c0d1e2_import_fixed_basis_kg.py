"""Partie fixe d'une route d'import répartie au kilo

Revision ID: f7a8b9c0d1e2
Revises: e6f7a8b9c0d1
Create Date: 2026-11-18 17:00:00.000000

La partie fixe (base_price) d'une route d'import — le forfait du transitaire
par expédition — n'était facturée nulle part : ni dans le prix de l'article,
ni au checkout (relecture du 17/11/2026). Elle est répartie au kilo facturé,
sur le poids d'un départ au seuil (décision du 18/11/2026).
"""

import sqlalchemy as sa
from alembic import op

revision = "f7a8b9c0d1e2"
down_revision = "e6f7a8b9c0d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "shipping_routes",
        sa.Column("import_fixed_basis_kg", sa.Numeric(10, 2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("shipping_routes", "import_fixed_basis_kg")
