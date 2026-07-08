"""add delivery_type to orders

Revision ID: a3b8d1f6c4e2
Revises: f7a1c3e9d2b5
Create Date: 2026-06-29 16:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a3b8d1f6c4e2"
down_revision = "f7a1c3e9d2b5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("delivery_type", sa.String(length=50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("orders", "delivery_type")
