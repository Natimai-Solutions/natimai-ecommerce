"""index des clés d'identité produit (EAN, UPC, référence fabricant)

Le rapprochement à l'import reconnaît désormais un article du même
fournisseur par son code-barres puis par marque + référence fabricant, en
plus de la référence fournisseur. Ces colonnes deviennent des clés de
recherche à chaque ligne importée : elles sont indexées.

Revision ID: f2b8d4a6c1e3
Revises: e1f7a3c9b5d2
Create Date: 2026-09-05 16:00:00.000000

"""

from alembic import op

revision = "f2b8d4a6c1e3"
down_revision = "e1f7a3c9b5d2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ix_products_ean", "products", ["ean"])
    op.create_index("ix_products_upc", "products", ["upc"])
    op.create_index(
        "ix_products_vendor_part_number", "products", ["vendor_part_number"]
    )


def downgrade() -> None:
    op.drop_index("ix_products_vendor_part_number", table_name="products")
    op.drop_index("ix_products_upc", table_name="products")
    op.drop_index("ix_products_ean", table_name="products")
