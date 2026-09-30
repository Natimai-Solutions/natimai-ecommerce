"""notifications de prestataires déjà traitées (R3-P4)

Revision ID: d3e6f9a2b5c8
Revises: c2d5e8f1a4b6
Create Date: 2026-09-30 11:00:00.000000

``payment_webhook_events`` : un événement de prestataire (PayPal…) n'est
appliqué qu'une fois, même livré plusieurs fois (unicité fournisseur +
identifiant d'événement).
"""

import sqlalchemy as sa
from alembic import op

revision = "d3e6f9a2b5c8"
down_revision = "c2d5e8f1a4b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_webhook_events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("provider_code", sa.String(length=50), nullable=False),
        sa.Column("event_id", sa.String(length=255), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=True),
        sa.Column("payment_id", sa.Uuid(), nullable=True),
        sa.Column("outcome", sa.String(length=30), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_code", "event_id", name="uq_payment_webhook_event_provider"
        ),
    )
    op.create_index(
        "ix_payment_webhook_events_payment_id",
        "payment_webhook_events",
        ["payment_id"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_payment_webhook_events_payment_id", table_name="payment_webhook_events"
    )
    op.drop_table("payment_webhook_events")
