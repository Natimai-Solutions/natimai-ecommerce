"""Phase 2 – group_upgrade_requests table

Revision ID: c5e3f9a2b7d1
Revises: b4c2d8e1f5a6
Create Date: 2026-06-08 00:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "c5e3f9a2b7d1"
down_revision = "b4c2d8e1f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "group_upgrade_requests",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("price_group_id", sa.UUID(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=20),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("business_registration_number", sa.String(length=100), nullable=False),
        sa.Column("attestation_notes", sa.String(length=2000), nullable=True),
        sa.Column("admin_comment", sa.String(length=1000), nullable=True),
        sa.Column("reviewed_by_id", sa.UUID(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["price_group_id"], ["price_groups.id"]),
        sa.ForeignKeyConstraint(["reviewed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_group_upgrade_requests_id", "group_upgrade_requests", ["id"], unique=False
    )
    op.create_index(
        "ix_group_upgrade_requests_user_id",
        "group_upgrade_requests",
        ["user_id"],
        unique=False,
    )
    op.create_index(
        "ix_group_upgrade_requests_price_group_id",
        "group_upgrade_requests",
        ["price_group_id"],
        unique=False,
    )
    op.create_index(
        "ix_group_upgrade_requests_status",
        "group_upgrade_requests",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_group_upgrade_requests_status", table_name="group_upgrade_requests")
    op.drop_index(
        "ix_group_upgrade_requests_price_group_id", table_name="group_upgrade_requests"
    )
    op.drop_index("ix_group_upgrade_requests_user_id", table_name="group_upgrade_requests")
    op.drop_index("ix_group_upgrade_requests_id", table_name="group_upgrade_requests")
    op.drop_table("group_upgrade_requests")
