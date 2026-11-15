"""mode d'import porté par la ligne de panier et la ligne de commande

Revision ID: a7b8c9d0e1f2
Revises: f6a7b8c9d0e1
Create Date: 2026-11-15 08:00:00.000000

Le prix d'un article importé comprend le fret de sa route d'import. Le panier
et la commande le calculaient sans route, donc sans fret, alors que la fiche
produit affichait le prix du mode choisi : le fret n'était facturé nulle part.
La ligne retient désormais le mode (``service_level``) sur lequel son prix est
calculé ; vide = la route d'import par défaut.
"""

import sqlalchemy as sa
from alembic import op

revision = "a7b8c9d0e1f2"
down_revision = "f6a7b8c9d0e1"
branch_labels = None
depends_on = None

_TABLES = ("cart_items", "order_lines")


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table, sa.Column("import_service_level", sa.String(50), nullable=True)
        )


def downgrade() -> None:
    for table in _TABLES:
        op.drop_column(table, "import_service_level")
