"""rename payment_log payzen columns to provider columns

Revision ID: 2d7f4b8c9e11
Revises: 1a2c9e5f7b31
Create Date: 2026-05-15 16:05:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "2d7f4b8c9e11"
down_revision = "1a2c9e5f7b31"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "payment_logs",
        "payzen_trans_id",
        new_column_name="provider_reference",
        existing_type=sa.String(),
    )
    op.alter_column(
        "payment_logs",
        "payzen_order_id",
        new_column_name="provider_order_reference",
        existing_type=sa.String(),
    )

    op.drop_index(op.f("ix_payment_logs_payzen_trans_id"), table_name="payment_logs")
    op.drop_index(op.f("ix_payment_logs_payzen_order_id"), table_name="payment_logs")
    op.create_index(
        op.f("ix_payment_logs_provider_reference"),
        "payment_logs",
        ["provider_reference"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_logs_provider_order_reference"),
        "payment_logs",
        ["provider_order_reference"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_payment_logs_provider_order_reference"),
        table_name="payment_logs",
    )
    op.drop_index(op.f("ix_payment_logs_provider_reference"), table_name="payment_logs")

    op.alter_column(
        "payment_logs",
        "provider_reference",
        new_column_name="payzen_trans_id",
        existing_type=sa.String(),
    )
    op.alter_column(
        "payment_logs",
        "provider_order_reference",
        new_column_name="payzen_order_id",
        existing_type=sa.String(),
    )

    op.create_index(
        op.f("ix_payment_logs_payzen_trans_id"),
        "payment_logs",
        ["payzen_trans_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payment_logs_payzen_order_id"),
        "payment_logs",
        ["payzen_order_id"],
        unique=False,
    )
