"""journal des e-mails envoyés : email_log

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-10-25 10:00:00.000000

Une ligne par message envoyé par la boutique (destinataire, objet, statut,
tentatives, fournisseur) : l'admin voit ce qui est parti et renvoie un
message. Le corps n'est gardé que pour un message renvoyable.
"""

import sqlalchemy as sa
from alembic import op

revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "email_log",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("recipient", sa.String(length=320), nullable=False),
        sa.Column("subject", sa.String(length=500), nullable=False),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("body_html", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("last_error", sa.String(length=500), nullable=True),
        sa.Column("provider_code", sa.String(length=50), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resendable", sa.Boolean(), nullable=False),
    )
    for column in ("created_at", "event_type", "recipient", "status"):
        op.create_index(f"ix_email_log_{column}", "email_log", [column])


def downgrade() -> None:
    op.drop_table("email_log")
