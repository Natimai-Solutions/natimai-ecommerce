"""liste blanche de références (SKU) par fournisseur

Revision ID: l3c9e6a1b4f7
Revises: k2b8d5f9a3e6
Create Date: 2026-09-26 18:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "l3c9e6a1b4f7"
down_revision = "k2b8d5f9a3e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("sku_allowlist", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("suppliers", "sku_allowlist")
