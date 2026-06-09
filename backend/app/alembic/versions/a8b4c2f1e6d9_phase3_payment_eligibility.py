"""phase3_payment_eligibility

Revision ID: a8b4c2f1e6d9
Revises: e7a5b3c9d1f2
Create Date: 2026-06-08

Adds optional max_amount to payment_methods and creates the
payment_method_eligibility join table (payment_method ↔ price_group).

Semantics: if a payment method has NO eligibility rows, it is available
to all price groups (backward-compatible open default). If at least one
row exists, only the listed groups may use it.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a8b4c2f1e6d9"
down_revision: str | None = "e7a5b3c9d1f2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "payment_methods",
        sa.Column(
            "max_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
            comment="Maximum transaction amount for this method (NULL = no limit)",
        ),
    )

    op.create_table(
        "payment_method_eligibility",
        sa.Column("payment_method_id", sa.UUID(), nullable=False),
        sa.Column("price_group_id", sa.UUID(), nullable=False),
        sa.ForeignKeyConstraint(
            ["payment_method_id"],
            ["payment_methods.id"],
            name="fk_pme_payment_method",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["price_group_id"],
            ["price_groups.id"],
            name="fk_pme_price_group",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("payment_method_id", "price_group_id"),
    )
    op.create_index(
        "ix_pme_price_group_id",
        "payment_method_eligibility",
        ["price_group_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_pme_price_group_id", table_name="payment_method_eligibility")
    op.drop_table("payment_method_eligibility")
    op.drop_column("payment_methods", "max_amount")
