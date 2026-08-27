"""add invoices, gap-free invoice counter and order currency (M3)

``invoices`` holds issued accounting documents (immutable: no soft-delete or
admin flags, no generic CRUD router). ``invoice_counters`` provides the
gap-free per-year numbering — a row locked with SELECT … FOR UPDATE inside the
issuing transaction, so a rollback releases the number instead of burning it
(unlike the order-number sequence added in e4b1c7d9a250).

``orders.currency`` freezes the billing currency at checkout; it is required
to invoice, and nullable for pre-existing orders (the invoice service then
falls back to the payment's currency).

Revision ID: f6d3a8b1c472
Revises: e4b1c7d9a250
Create Date: 2026-08-25 16:30:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "f6d3a8b1c472"
down_revision = "e4b1c7d9a250"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "orders",
        sa.Column("currency", sa.String(length=8), nullable=True),
    )

    op.create_table(
        "invoice_counters",
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("fiscal_year"),
    )

    op.create_table(
        "invoices",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("invoice_number", sa.String(length=32), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("total_excl_tax", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_tax", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("total_incl_tax", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        # One invoice per order — the DB enforces the idempotency the service
        # relies on, even under concurrent payment.captured deliveries.
        sa.UniqueConstraint("order_id", name="uq_invoices_order_id"),
        sa.UniqueConstraint("invoice_number", name="uq_invoices_invoice_number"),
    )
    op.create_index("ix_invoices_id", "invoices", ["id"])
    op.create_index("ix_invoices_invoice_number", "invoices", ["invoice_number"])
    op.create_index("ix_invoices_fiscal_year", "invoices", ["fiscal_year"])
    op.create_index("ix_invoices_order_id", "invoices", ["order_id"])
    op.create_index("ix_invoices_user_id", "invoices", ["user_id"])
    op.create_index("ix_invoices_issued_at", "invoices", ["issued_at"])


def downgrade() -> None:
    op.drop_index("ix_invoices_issued_at", table_name="invoices")
    op.drop_index("ix_invoices_user_id", table_name="invoices")
    op.drop_index("ix_invoices_order_id", table_name="invoices")
    op.drop_index("ix_invoices_fiscal_year", table_name="invoices")
    op.drop_index("ix_invoices_invoice_number", table_name="invoices")
    op.drop_index("ix_invoices_id", table_name="invoices")
    op.drop_table("invoices")
    op.drop_table("invoice_counters")
    op.drop_column("orders", "currency")
