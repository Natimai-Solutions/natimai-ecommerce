"""add_order_cgv_acceptance

Records the customer's acceptance of the terms of sale on the order itself.
The checkout checkbox alone proves nothing: it is client-side and an API call
bypasses it entirely. Nullable on purpose — orders created before this change
have no acceptance to backfill, and inventing one would be worse than a NULL.

Revision ID: c4d8e2a1f9b3
Revises: a9c5e1f3b7d2
Create Date: 2026-08-27 00:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "c4d8e2a1f9b3"
down_revision = "a9c5e1f3b7d2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "orders",
        sa.Column("cgv_accepted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "orders",
        sa.Column("cgv_version", sa.String(length=50), nullable=True),
    )


def downgrade():
    op.drop_column("orders", "cgv_version")
    op.drop_column("orders", "cgv_accepted_at")
