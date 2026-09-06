"""clé d'identité produit et prix vitrine matérialisé

La recherche vitrine calculait le prix de chaque produit à la volée et
regroupait les « autres offres » en mémoire : son coût suivait le nombre de
produits filtrés, pas la page. Deux colonnes la ramènent en SQL :

* ``products.identity_key`` — clé « même produit physique » (code-barres
  canonique, sinon marque + référence fabricant), maintenue par un écouteur
  ORM à chaque écriture ; remplie ici pour l'existant ;
* ``products.sale_price_cached`` (+ ``_at``) — prix de liste matérialisé,
  posé par le CRUD produit, la tâche de rafraîchissement et le cron nocturne.
  Laissé à NULL ici : la recherche tarifie à la volée les lignes non encore
  calculées et les persiste au passage.

Revision ID: a7c3e9f1b2d4
Revises: f2b8d4a6c1e3
Create Date: 2026-09-05 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

from app.features.product.services.identity import product_identity_key

revision = "a7c3e9f1b2d4"
down_revision = "f2b8d4a6c1e3"
branch_labels = None
depends_on = None

_BATCH = 1000


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("identity_key", sa.String(length=200), nullable=True)
    )
    op.add_column(
        "products",
        sa.Column("sale_price_cached", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "products", sa.Column("sale_price_cached_at", sa.DateTime(), nullable=True)
    )
    op.create_index("ix_products_identity_key", "products", ["identity_key"])
    op.create_index("ix_products_sale_price_cached", "products", ["sale_price_cached"])

    bind = op.get_bind()
    products = sa.table(
        "products",
        sa.column("id", sa.Uuid()),
        sa.column("ean", sa.String()),
        sa.column("upc", sa.String()),
        sa.column("manufacturer", sa.String()),
        sa.column("vendor_part_number", sa.String()),
        sa.column("identity_key", sa.String()),
    )
    offset = 0
    while True:
        rows = bind.execute(
            sa.select(
                products.c.id,
                products.c.ean,
                products.c.upc,
                products.c.manufacturer,
                products.c.vendor_part_number,
            )
            .order_by(products.c.id)
            .offset(offset)
            .limit(_BATCH)
        ).all()
        if not rows:
            break
        for row in rows:
            key = product_identity_key(row)
            if key is not None:
                bind.execute(
                    products.update()
                    .where(products.c.id == row.id)
                    .values(identity_key=key)
                )
        offset += _BATCH


def downgrade() -> None:
    op.drop_index("ix_products_sale_price_cached", table_name="products")
    op.drop_index("ix_products_identity_key", table_name="products")
    op.drop_column("products", "sale_price_cached_at")
    op.drop_column("products", "sale_price_cached")
    op.drop_column("products", "identity_key")
