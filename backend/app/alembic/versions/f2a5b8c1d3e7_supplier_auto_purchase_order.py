"""fournisseurs : commande fournisseur automatique par fournisseur (R4 / S4)

Revision ID: f2a5b8c1d3e7
Revises: e1f4a7b9c2d6
Create Date: 2026-10-01 12:00:00.000000

``suppliers.auto_purchase_order`` : la commande fournisseur part à
l'encaissement pour tout fournisseur dont l'intégration sait commander
(faux pour l'existant ; Ingram reste aussi piloté par
``INGRAM_ORDER_CREATION_ENABLED``).
"""

import sqlalchemy as sa
from alembic import op

revision = "f2a5b8c1d3e7"
down_revision = "e1f4a7b9c2d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "suppliers",
        sa.Column(
            "auto_purchase_order",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("suppliers", "auto_purchase_order")
