"""traitements d'événements abandonnés

Revision ID: c9d0e1f2a3b4
Revises: b8c9d0e1f2a3
Create Date: 2026-11-16 21:00:00.000000

Un traitement abandonné après toutes ses tentatives ne laissait qu'un log et
une alerte : l'événement est « DONE ». La ligne permet de le voir et de le
rejouer depuis l'admin (État du système).
"""

import sqlalchemy as sa
from alembic import op

revision = "c9d0e1f2a3b4"
down_revision = "b8c9d0e1f2a3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "outbox_handler_failures",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("event_id", sa.Uuid(), nullable=False, index=True),
        sa.Column("event_type", sa.String(), nullable=False, index=True),
        sa.Column("handler_path", sa.String(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("tries", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolution", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("outbox_handler_failures")
