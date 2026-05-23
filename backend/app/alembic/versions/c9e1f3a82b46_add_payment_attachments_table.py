"""add payment_attachments table

Revision ID: c9e1f3a82b46
Revises: b8c4f2a9d317
Create Date: 2026-05-15 11:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "c9e1f3a82b46"
down_revision = "b8c4f2a9d317"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_attachments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("payment_id", sa.Uuid(), nullable=False),
        sa.Column("file_key", sa.String(length=512), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("mimetype", sa.String(length=100), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("document_type", sa.String(length=50), nullable=False),
        sa.Column("uploaded_by_user_id", sa.Uuid(), nullable=True),
        sa.Column(
            "av_scanned",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("av_clean", sa.Boolean(), nullable=True),
        sa.Column("av_signature", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "is_admin_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["payment_id"], ["payments.id"]),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_payment_attachments_id"),
        "payment_attachments",
        ["id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_attachments_payment_id"),
        "payment_attachments",
        ["payment_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_attachments_file_key"),
        "payment_attachments",
        ["file_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_attachments_document_type"),
        "payment_attachments",
        ["document_type"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_attachments_uploaded_by_user_id"),
        "payment_attachments",
        ["uploaded_by_user_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_payment_attachments_uploaded_by_user_id"),
        table_name="payment_attachments",
    )
    op.drop_index(
        op.f("ix_payment_attachments_document_type"),
        table_name="payment_attachments",
    )
    op.drop_index(
        op.f("ix_payment_attachments_file_key"),
        table_name="payment_attachments",
    )
    op.drop_index(
        op.f("ix_payment_attachments_payment_id"),
        table_name="payment_attachments",
    )
    op.drop_index(
        op.f("ix_payment_attachments_id"),
        table_name="payment_attachments",
    )
    op.drop_table("payment_attachments")
