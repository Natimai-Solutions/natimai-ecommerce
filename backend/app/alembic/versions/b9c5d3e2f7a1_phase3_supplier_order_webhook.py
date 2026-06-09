"""phase3_supplier_order_webhook

Revision ID: b9c5d3e2f7a1
Revises: a8b4c2f1e6d9
Create Date: 2026-06-08

Adds estimated_delivery timestamp to supplier_orders so the Ingram
webhook can store the delivery estimate returned by the supplier.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b9c5d3e2f7a1"
down_revision: str | None = "a8b4c2f1e6d9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "supplier_orders",
        sa.Column(
            "estimated_delivery",
            sa.DateTime(timezone=True),
            nullable=True,
            comment="Estimated delivery date returned by the supplier webhook",
        ),
    )


def downgrade() -> None:
    op.drop_column("supplier_orders", "estimated_delivery")
