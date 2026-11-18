"""Messagerie : conversations et messages

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-11-19 00:30:00.000000

Un client écrit au service client, au support technique ou au service
commercial ; l'équipe répond dans l'administration (chantier accueil et
messagerie, lot MSG1). Préférence `notification_messages` : l'avis par e-mail
d'une réponse, sans son contenu.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SEQUENCE IF NOT EXISTS conversation_number_seq")
    op.create_table(
        "conversations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("number", sa.String(length=20), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=False),
        sa.Column("topic", sa.String(length=30), nullable=False),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("customer_id", sa.Uuid(), nullable=True),
        sa.Column("guest_name", sa.String(length=255), nullable=True),
        sa.Column("guest_email", sa.String(length=255), nullable=True),
        sa.Column("guest_phone", sa.String(length=50), nullable=True),
        sa.Column("guest_company", sa.String(length=255), nullable=True),
        sa.Column("guest_locale", sa.String(length=10), nullable=True),
        sa.Column("context_type", sa.String(length=30), nullable=True),
        sa.Column("context_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_to_id", sa.Uuid(), nullable=True),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_customer_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_staff_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("customer_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("staff_notified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_staff_reply_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retain_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deletion_notice_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assigned_to_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_conversations_number", "conversations", ["number"], unique=True)
    for column in (
        "channel",
        "status",
        "customer_id",
        "guest_email",
        "context_id",
        "assigned_to_id",
        "last_message_at",
    ):
        op.create_index(f"ix_conversations_{column}", "conversations", [column])
    op.create_table(
        "conversation_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("conversation_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=True),
        sa.Column("side", sa.String(length=20), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "data",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_conversation_messages_conversation_id",
        "conversation_messages",
        ["conversation_id"],
    )
    op.create_index(
        "ix_conversation_messages_created_at", "conversation_messages", ["created_at"]
    )
    op.add_column(
        "user_preferences",
        sa.Column(
            "notification_messages",
            sa.Boolean(),
            nullable=False,
            server_default="true",
        ),
    )


def downgrade() -> None:
    op.drop_column("user_preferences", "notification_messages")
    op.drop_table("conversation_messages")
    op.drop_table("conversations")
    op.execute("DROP SEQUENCE IF EXISTS conversation_number_seq")
