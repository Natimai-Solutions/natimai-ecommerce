"""variantes d'articles : une variante est une ligne products rattachée à un parent

Une déclinaison (taille, couleur…) a son propre SKU, prix, coût, stock,
image, poids et mapping fournisseur : tout ce qu'une ligne ``products``
porte déjà et que le panier, la commande, l'inventaire et la facture savent
référencer. Elle est donc une ligne ``products`` de plus, liée à son parent
par ``parent_product_id`` et décrite par ``variant_options``
({"Taille": "M", "Couleur": "Noir"}). Le parent (``has_variants``) est
l'entrée vitrine : listé, jamais vendu tel quel.

Revision ID: f3d8e1b6c4a2
Revises: e2c7d9a5b3f1
Create Date: 2026-09-10 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "f3d8e1b6c4a2"
down_revision = "e2c7d9a5b3f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("products", sa.Column("parent_product_id", sa.Uuid(), nullable=True))
    op.add_column("products", sa.Column("variant_options", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_products_parent_product_id",
        "products",
        "products",
        ["parent_product_id"],
        ["id"],
    )
    op.create_index(
        "ix_products_parent_product_id", "products", ["parent_product_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_products_parent_product_id", table_name="products")
    op.drop_constraint("fk_products_parent_product_id", "products", type_="foreignkey")
    op.drop_column("products", "variant_options")
    op.drop_column("products", "parent_product_id")
