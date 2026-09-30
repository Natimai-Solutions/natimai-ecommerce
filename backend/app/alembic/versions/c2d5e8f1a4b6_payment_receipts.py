"""versements reçus sur un paiement manuel (R3-P2)

Revision ID: c2d5e8f1a4b6
Revises: b1c4d7e2f9a3
Create Date: 2026-09-30 10:00:00.000000

``payment_receipts`` : chaque somme reçue au titre d'un paiement manuel
(versements en espèces, chèque encaissé, virement). Le paiement est soldé
quand la somme des versements actifs atteint son montant ; un versement
annulé (chèque impayé) garde sa trace (``is_active`` faux, motif).
"""

import sqlalchemy as sa
from alembic import op

revision = "c2d5e8f1a4b6"
down_revision = "b1c4d7e2f9a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_receipts",
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=10), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(length=20), nullable=False),
        sa.Column("reference", sa.String(length=100), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("recorded_by_id", sa.Uuid(), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_by_id", sa.Uuid(), nullable=True),
        sa.Column("cancel_reason", sa.String(length=500), nullable=True),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["recorded_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["cancelled_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_payment_receipts_payment_id", "payment_receipts", ["payment_id"]
    )
    op.create_index("ix_payment_receipts_order_id", "payment_receipts", ["order_id"])


def downgrade() -> None:
    op.drop_index("ix_payment_receipts_order_id", table_name="payment_receipts")
    op.drop_index("ix_payment_receipts_payment_id", table_name="payment_receipts")
    op.drop_table("payment_receipts")
