"""prix par groupe : remise du groupe et prix saisis par article

Revision ID: b7c1d4e6f9a3
Revises: a6b9c3d5e8f2
Create Date: 2026-09-30 19:00:00.000000

* ``price_groups.discount_pct`` : remise du groupe en % du prix de référence
  (0 pour les groupes existants : aucun prix ne change) ;
* ``product_group_prices`` : prix TTC d'un article pour un groupe, qui passe
  avant la remise.
"""

import sqlalchemy as sa
from alembic import op

revision = "b7c1d4e6f9a3"
down_revision = "a6b9c3d5e8f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_groups",
        sa.Column(
            "discount_pct",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.create_table(
        "product_group_prices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("product_id", sa.Uuid(), nullable=False),
        sa.Column("price_group_id", sa.Uuid(), nullable=False),
        sa.Column("price", sa.Numeric(precision=14, scale=2), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["price_group_id"], ["price_groups.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "product_id", "price_group_id", name="uq_product_group_price"
        ),
    )
    op.create_index(
        "ix_product_group_prices_product_id", "product_group_prices", ["product_id"]
    )
    op.create_index(
        "ix_product_group_prices_price_group_id",
        "product_group_prices",
        ["price_group_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_group_prices_price_group_id", table_name="product_group_prices"
    )
    op.drop_index(
        "ix_product_group_prices_product_id", table_name="product_group_prices"
    )
    op.drop_table("product_group_prices")
    op.drop_column("price_groups", "discount_pct")
