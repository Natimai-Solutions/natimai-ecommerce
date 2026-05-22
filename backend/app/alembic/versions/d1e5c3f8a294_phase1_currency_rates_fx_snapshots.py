"""phase1 currency rates and fx snapshots

Revision ID: d1e5c3f8a294
Revises: 8c2f1d4a6e90
Create Date: 2026-05-22 12:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "d1e5c3f8a294"
down_revision = "8c2f1d4a6e90"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "currency_rates",
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.Column("currency_code", sa.String(length=8), nullable=False),
        sa.Column("rate_to_xpf", sa.Numeric(precision=16, scale=6), nullable=False),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_until", sa.Date(), nullable=True),
        sa.Column("source", sa.String(length=16), nullable=False, server_default="manual"),
        sa.Column("updated_by_user_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["updated_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_currency_rates_id"), "currency_rates", ["id"], unique=False)
    op.create_index(
        op.f("ix_currency_rates_currency_code"), "currency_rates", ["currency_code"], unique=False
    )
    op.create_index(
        "ix_currency_rates_code_active",
        "currency_rates",
        ["currency_code", "valid_from", "valid_until"],
        unique=False,
    )

    # CartItem FX snapshots
    op.add_column("cart_items", sa.Column("fx_source_currency", sa.String(length=8), nullable=True))
    op.add_column(
        "cart_items",
        sa.Column("fx_rate_used", sa.Numeric(precision=16, scale=6), nullable=True),
    )

    # OrderLine FX + pricing snapshots
    op.add_column(
        "order_lines",
        sa.Column("cost_amount_snapshot", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "order_lines", sa.Column("cost_currency_snapshot", sa.String(length=8), nullable=True)
    )
    op.add_column(
        "order_lines",
        sa.Column("fx_rate_used", sa.Numeric(precision=16, scale=6), nullable=True),
    )
    op.add_column(
        "order_lines",
        sa.Column("customs_rate_pct_snapshot", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column(
        "order_lines",
        sa.Column("margin_rate_pct_snapshot", sa.Numeric(precision=8, scale=2), nullable=True),
    )
    op.add_column("order_lines", sa.Column("price_group_id_snapshot", sa.Uuid(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_lines", "price_group_id_snapshot")
    op.drop_column("order_lines", "margin_rate_pct_snapshot")
    op.drop_column("order_lines", "customs_rate_pct_snapshot")
    op.drop_column("order_lines", "fx_rate_used")
    op.drop_column("order_lines", "cost_currency_snapshot")
    op.drop_column("order_lines", "cost_amount_snapshot")

    op.drop_column("cart_items", "fx_rate_used")
    op.drop_column("cart_items", "fx_source_currency")

    op.drop_index("ix_currency_rates_code_active", table_name="currency_rates")
    op.drop_index(op.f("ix_currency_rates_currency_code"), table_name="currency_rates")
    op.drop_index(op.f("ix_currency_rates_id"), table_name="currency_rates")
    op.drop_table("currency_rates")
