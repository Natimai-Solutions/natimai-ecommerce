"""add overridden_fields to products

Revision ID: c7d2f4a9e5b1
Revises: b5c9e2a7f1d3
Create Date: 2026-07-01 09:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c7d2f4a9e5b1"
down_revision = "b5c9e2a7f1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("overridden_fields", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "overridden_fields")
