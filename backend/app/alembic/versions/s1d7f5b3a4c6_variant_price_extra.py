"""suppléments de variante (R9 / T6) : products.price_extra

Revision ID: s1d7f5b3a4c6
Revises: r9c6e4a2f3b5
Create Date: 2026-10-02 05:00:00.000000

Une variante peut porter un supplément sur le prix de sa fiche parente
(« i7 : + 10 000 F ») : son prix est alors recalculé quand le prix parent
change, et la vitrine affiche « + 10 000 F » dans le sélecteur.
"""

import sqlalchemy as sa
from alembic import op

revision = "s1d7f5b3a4c6"
down_revision = "r9c6e4a2f3b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("price_extra", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "price_extra")
