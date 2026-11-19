"""Messagerie : pièces jointes

Revision ID: a5c6d7e8f9a0
Revises: f4b5c6d7e8f9
Create Date: 2026-11-19 02:30:00.000000

Photos et PDF joints aux messages : type lu sur les octets, antivirus à
l'envoi, images réencodées sans métadonnées (chantier accueil et messagerie,
lot MSG1).
"""

import sqlalchemy as sa
from alembic import op

revision = "a5c6d7e8f9a0"
down_revision = "f4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversation_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["message_id"], ["conversation_messages.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_attachments_conversation_id",
        "conversation_attachments",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_attachments_message_id",
        "conversation_attachments",
        ["message_id"],
    )


def downgrade() -> None:
    op.drop_table("conversation_attachments")
