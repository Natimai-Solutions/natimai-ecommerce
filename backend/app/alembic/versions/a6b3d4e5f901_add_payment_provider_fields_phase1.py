"""add generic payment provider fields phase 1

Revision ID: a6b3d4e5f901
Revises: f1e9c2a7b4d1
Create Date: 2026-05-13 11:10:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "a6b3d4e5f901"
down_revision = "f1e9c2a7b4d1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "payments",
        sa.Column(
            "provider_code",
            sa.String(length=50),
            nullable=False,
            server_default="payzen",
        ),
    )
    op.add_column(
        "payments",
        sa.Column("provider_reference", sa.String(length=255), nullable=True),
    )
    op.add_column(
        "payments",
        sa.Column("provider_data", sa.JSON(), nullable=True),
    )
    op.create_index(
        op.f("ix_payments_provider_code"),
        "payments",
        ["provider_code"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payments_provider_reference"),
        "payments",
        ["provider_reference"],
        unique=False,
    )
    op.alter_column("payments", "provider_code", server_default=None)

    op.add_column(
        "payment_methods",
        sa.Column(
            "provider_code",
            sa.String(length=50),
            nullable=False,
            server_default="payzen",
        ),
    )
    op.add_column(
        "payment_methods",
        sa.Column(
            "requires_admin_validation",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "payment_methods",
        sa.Column(
            "requires_document_upload",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )
    op.add_column(
        "payment_methods",
        sa.Column(
            "sort_order",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("0"),
        ),
    )
    op.create_index(
        op.f("ix_payment_methods_provider_code"),
        "payment_methods",
        ["provider_code"],
        unique=False,
    )
    op.alter_column("payment_methods", "provider_code", server_default=None)
    op.alter_column(
        "payment_methods",
        "requires_admin_validation",
        server_default=None,
    )
    op.alter_column(
        "payment_methods",
        "requires_document_upload",
        server_default=None,
    )
    op.alter_column("payment_methods", "sort_order", server_default=None)


def downgrade() -> None:
    op.drop_index(
        op.f("ix_payment_methods_provider_code"),
        table_name="payment_methods",
    )
    op.drop_column("payment_methods", "sort_order")
    op.drop_column("payment_methods", "requires_document_upload")
    op.drop_column("payment_methods", "requires_admin_validation")
    op.drop_column("payment_methods", "provider_code")

    op.drop_index(op.f("ix_payments_provider_reference"), table_name="payments")
    op.drop_index(op.f("ix_payments_provider_code"), table_name="payments")
    op.drop_column("payments", "provider_data")
    op.drop_column("payments", "provider_reference")
    op.drop_column("payments", "provider_code")
