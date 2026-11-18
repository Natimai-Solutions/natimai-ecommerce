"""Messagerie : lien « continuer sur le site » d'un visiteur

Revision ID: b6d7e8f9a0b1
Revises: a5c6d7e8f9a0
Create Date: 2026-11-19 03:30:00.000000

La réponse de l'équipe à un visiteur sans compte part par e-mail avec un lien
d'inscription ; le jeton est gardé en condensat SHA-256 (lot MSG2).
"""

import sqlalchemy as sa
from alembic import op

revision = "b6d7e8f9a0b1"
down_revision = "a5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "conversations",
        sa.Column("guest_token_hash", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "conversations",
        sa.Column(
            "guest_token_expires_at", sa.DateTime(timezone=True), nullable=True
        ),
    )
    op.create_index(
        "ix_conversations_guest_token_hash", "conversations", ["guest_token_hash"]
    )


def downgrade() -> None:
    op.drop_index("ix_conversations_guest_token_hash", table_name="conversations")
    op.drop_column("conversations", "guest_token_expires_at")
    op.drop_column("conversations", "guest_token_hash")
