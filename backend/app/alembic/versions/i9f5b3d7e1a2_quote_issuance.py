"""devis émis : numéro DEV, validité, snapshot, commande issue du devis

Revision ID: i9f5b3d7e1a2
Revises: h8e4a2c6d9f1
Create Date: 2026-09-26 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "i9f5b3d7e1a2"
down_revision = "h8e4a2c6d9f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "quote_counters",
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("fiscal_year"),
    )
    op.add_column(
        "quote_requests", sa.Column("quote_number", sa.String(length=32), nullable=True)
    )
    op.add_column(
        "quote_requests", sa.Column("quoted_at", sa.DateTime(), nullable=True)
    )
    op.add_column("quote_requests", sa.Column("valid_until", sa.Date(), nullable=True))
    op.add_column(
        "quote_requests", sa.Column("quote_snapshot", sa.JSON(), nullable=True)
    )
    op.add_column("quote_requests", sa.Column("order_id", sa.Uuid(), nullable=True))
    op.create_index(
        op.f("ix_quote_requests_quote_number"),
        "quote_requests",
        ["quote_number"],
        unique=True,
    )
    op.create_foreign_key(
        "fk_quote_requests_order_id", "quote_requests", "orders", ["order_id"], ["id"]
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_quote_requests_order_id", "quote_requests", type_="foreignkey"
    )
    op.drop_index(op.f("ix_quote_requests_quote_number"), table_name="quote_requests")
    for column in (
        "order_id",
        "quote_snapshot",
        "valid_until",
        "quoted_at",
        "quote_number",
    ):
        op.drop_column("quote_requests", column)
    op.drop_table("quote_counters")
