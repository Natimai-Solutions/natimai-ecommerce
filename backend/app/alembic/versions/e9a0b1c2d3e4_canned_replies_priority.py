"""Messagerie : réponses types et groupes prioritaires

Revision ID: e9a0b1c2d3e4
Revises: d8f9a0b1c2d3
Create Date: 2026-11-19 06:30:00.000000

Réponses préparées de l'équipe, traduites ; case « prioritaire dans la
messagerie » sur un groupe tarifaire (lot MSG4).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "e9a0b1c2d3e4"
down_revision = "d8f9a0b1c2d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "canned_replies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("channel", sa.String(length=30), nullable=True),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column(
            "translations",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default="{}",
        ),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.add_column(
        "price_groups",
        sa.Column(
            "messaging_priority",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )


def downgrade() -> None:
    op.drop_column("price_groups", "messaging_priority")
    op.drop_table("canned_replies")
