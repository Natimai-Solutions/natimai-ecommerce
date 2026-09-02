"""add credit notes and their gap-free counter (Z2)

A refund changed a payment status and nothing else: the money went back while
the invoice stayed in the books claiming a sale that no longer held. An issued
invoice is immutable and its sequence gap-free, so the correction is a second
document referencing the first.

``credit_note_counters`` is a table of its own rather than a new key on
``invoice_counters``: the two sequences are legally distinct and must never
share numbers.

``refund_id`` is unique — it is the idempotency key, the outbox guaranteeing
at-least-once delivery of ``payment.refunded``.

Revision ID: d3b8c5f1a742
Revises: c8f1a4d6e920
Create Date: 2026-09-02 12:20:00.000000

"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "d3b8c5f1a742"
down_revision = "c8f1a4d6e920"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "credit_note_counters",
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("fiscal_year"),
    )

    op.create_table(
        "credit_notes",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("credit_note_number", sa.String(length=32), nullable=False),
        sa.Column("fiscal_year", sa.Integer(), nullable=False),
        sa.Column("sequence_number", sa.Integer(), nullable=False),
        sa.Column("invoice_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("refund_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("issued_at", sa.DateTime(), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("total_excl_tax", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_tax", sa.Numeric(12, 2), nullable=False),
        sa.Column("total_incl_tax", sa.Numeric(12, 2), nullable=False),
        sa.Column("reason", sa.String(length=1024), nullable=True),
        sa.Column("snapshot", sa.JSON(), nullable=False),
        sa.Column("emailed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"]),
        sa.ForeignKeyConstraint(["refund_id"], ["refunds.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("credit_note_number"),
        sa.UniqueConstraint("refund_id"),
    )
    op.create_index("ix_credit_notes_id", "credit_notes", ["id"])
    op.create_index(
        "ix_credit_notes_credit_note_number", "credit_notes", ["credit_note_number"]
    )
    op.create_index("ix_credit_notes_fiscal_year", "credit_notes", ["fiscal_year"])
    op.create_index("ix_credit_notes_invoice_id", "credit_notes", ["invoice_id"])
    op.create_index("ix_credit_notes_order_id", "credit_notes", ["order_id"])
    op.create_index("ix_credit_notes_user_id", "credit_notes", ["user_id"])
    op.create_index("ix_credit_notes_issued_at", "credit_notes", ["issued_at"])


def downgrade() -> None:
    op.drop_table("credit_notes")
    op.drop_table("credit_note_counters")
