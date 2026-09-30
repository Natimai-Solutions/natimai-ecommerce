"""acompte à la commande : politique par groupe tarifaire, plan de paiement

Revision ID: h8e4a2c6d9f1
Revises: g7d3f9a1b5c2
Create Date: 2026-09-25 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "h8e4a2c6d9f1"
down_revision = "g7d3f9a1b5c2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "price_groups",
        sa.Column("deposit_pct", sa.Numeric(precision=5, scale=2), nullable=True),
    )
    op.add_column(
        "price_groups",
        sa.Column(
            "deposit_fee_pct",
            sa.Numeric(precision=5, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "price_groups",
        sa.Column(
            "deposit_fee_fixed",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "price_groups",
        sa.Column(
            "deposit_required",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "payment_plan", sa.String(length=20), nullable=False, server_default="full"
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "deposit_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "orders",
        sa.Column(
            "deposit_fee_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "orders", sa.Column("balance_requested_at", sa.DateTime(), nullable=True)
    )
    op.add_column("orders", sa.Column("balance_paid_at", sa.DateTime(), nullable=True))
    op.add_column(
        "payments",
        sa.Column("kind", sa.String(length=20), nullable=False, server_default="full"),
    )


def downgrade() -> None:
    op.drop_column("payments", "kind")
    for column in (
        "balance_paid_at",
        "balance_requested_at",
        "deposit_fee_amount",
        "deposit_amount",
        "payment_plan",
    ):
        op.drop_column("orders", column)
    for column in (
        "deposit_required",
        "deposit_fee_fixed",
        "deposit_fee_pct",
        "deposit_pct",
    ):
        op.drop_column("price_groups", column)
