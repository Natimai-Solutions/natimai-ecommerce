"""marge : coût de revient et marge matérialisés, coût de revient par ligne

Revision ID: a6b9c3d5e8f2
Revises: f5a8b2c4d7e1
Create Date: 2026-09-30 17:00:00.000000

* ``products.unit_cost_cached`` / ``margin_cached`` / ``margin_pct_cached`` :
  coût de revient HT, marge HT et taux de marque, recalculés avec
  ``sale_price_cached`` (liste admin triable par marge) ;
* ``order_lines.unit_cost_snapshot`` : coût de revient unitaire HT figé à la
  commande (marge de la commande dans l'admin).

Les produits existants sont remplis par le recalcul des prix (nuit, ou
« Recalculer les prix » dans l'admin).
"""

import sqlalchemy as sa
from alembic import op

revision = "a6b9c3d5e8f2"
down_revision = "f5a8b2c4d7e1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("unit_cost_cached", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("margin_cached", sa.Numeric(precision=14, scale=2), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("margin_pct_cached", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column(
        "order_lines",
        sa.Column(
            "unit_cost_snapshot", sa.Numeric(precision=14, scale=2), nullable=True
        ),
    )


def downgrade() -> None:
    op.drop_column("order_lines", "unit_cost_snapshot")
    op.drop_column("products", "margin_pct_cached")
    op.drop_column("products", "margin_cached")
    op.drop_column("products", "unit_cost_cached")
