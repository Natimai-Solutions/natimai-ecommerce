"""drop legacy payzen columns from payments

Revision ID: 1a2c9e5f7b31
Revises: c9e1f3a82b46
Create Date: 2026-05-15 14:35:00.000000

"""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "1a2c9e5f7b31"
down_revision = "c9e1f3a82b46"
branch_labels = None
depends_on = None


def _as_provider_data(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return dict(raw)
    return {}


def upgrade() -> None:
    bind = op.get_bind()

    payments = sa.table(
        "payments",
        sa.column("id", sa.Uuid()),
        sa.column("provider_code", sa.String(length=50)),
        sa.column("provider_reference", sa.String(length=255)),
        sa.column("provider_data", sa.JSON()),
        sa.column("payzen_trans_id", sa.String()),
        sa.column("payzen_order_id", sa.String()),
        sa.column("payzen_payment_method", sa.String()),
        sa.column("payzen_status", sa.String()),
        sa.column("payzen_error_code", sa.String()),
        sa.column("payzen_form_token", sa.String()),
        sa.column("payzen_data", sa.JSON()),
    )

    rows = bind.execute(
        sa.select(
            payments.c.id,
            payments.c.provider_code,
            payments.c.provider_reference,
            payments.c.provider_data,
            payments.c.payzen_trans_id,
            payments.c.payzen_order_id,
            payments.c.payzen_payment_method,
            payments.c.payzen_status,
            payments.c.payzen_error_code,
            payments.c.payzen_form_token,
            payments.c.payzen_data,
        )
    ).mappings()

    for row in rows:
        trans_id = row["payzen_trans_id"]
        order_id = row["payzen_order_id"]
        payment_cards = row["payzen_payment_method"]
        trans_status = row["payzen_status"]
        error_code = row["payzen_error_code"]
        form_token = row["payzen_form_token"]
        raw_answer = row["payzen_data"]

        provider_data = _as_provider_data(row["provider_data"])
        if trans_id is not None:
            provider_data["trans_id"] = trans_id
            provider_data["trans_uuid"] = trans_id
        if order_id is not None:
            provider_data["order_id"] = order_id
        if payment_cards is not None:
            provider_data["payment_cards"] = payment_cards
        if trans_status is not None:
            provider_data["trans_status"] = trans_status
        if error_code is not None:
            provider_data["error_code"] = error_code
        if form_token is not None:
            provider_data["form_token"] = form_token
        if raw_answer is not None:
            provider_data["_raw_answer"] = raw_answer

        provider_code = row["provider_code"] or "payzen"
        provider_reference = row["provider_reference"] or order_id or trans_id

        bind.execute(
            sa.update(payments)
            .where(payments.c.id == row["id"])
            .values(
                provider_code=provider_code,
                provider_reference=provider_reference,
                provider_data=provider_data or None,
            )
        )

    op.drop_index(op.f("ix_payments_payzen_order_id"), table_name="payments")
    op.drop_index(op.f("ix_payments_payzen_trans_id"), table_name="payments")

    op.drop_column("payments", "payzen_data")
    op.drop_column("payments", "payzen_form_token")
    op.drop_column("payments", "payzen_error_code")
    op.drop_column("payments", "payzen_status")
    op.drop_column("payments", "payzen_payment_method")
    op.drop_column("payments", "payzen_order_id")
    op.drop_column("payments", "payzen_trans_id")


def downgrade() -> None:
    bind = op.get_bind()

    op.add_column("payments", sa.Column("payzen_trans_id", sa.String(), nullable=True))
    op.add_column("payments", sa.Column("payzen_order_id", sa.String(), nullable=True))
    op.add_column(
        "payments", sa.Column("payzen_payment_method", sa.String(), nullable=True)
    )
    op.add_column("payments", sa.Column("payzen_status", sa.String(), nullable=True))
    op.add_column("payments", sa.Column("payzen_error_code", sa.String(), nullable=True))
    op.add_column("payments", sa.Column("payzen_form_token", sa.String(), nullable=True))
    op.add_column("payments", sa.Column("payzen_data", sa.JSON(), nullable=True))

    op.create_index(
        op.f("ix_payments_payzen_trans_id"),
        "payments",
        ["payzen_trans_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_payments_payzen_order_id"),
        "payments",
        ["payzen_order_id"],
        unique=False,
    )

    payments = sa.table(
        "payments",
        sa.column("id", sa.Uuid()),
        sa.column("provider_reference", sa.String(length=255)),
        sa.column("provider_data", sa.JSON()),
        sa.column("payzen_trans_id", sa.String()),
        sa.column("payzen_order_id", sa.String()),
        sa.column("payzen_payment_method", sa.String()),
        sa.column("payzen_status", sa.String()),
        sa.column("payzen_error_code", sa.String()),
        sa.column("payzen_form_token", sa.String()),
        sa.column("payzen_data", sa.JSON()),
    )

    rows = bind.execute(
        sa.select(
            payments.c.id,
            payments.c.provider_reference,
            payments.c.provider_data,
        )
    ).mappings()

    for row in rows:
        provider_data = _as_provider_data(row["provider_data"])

        trans_id = provider_data.get("trans_uuid") or provider_data.get("trans_id")
        order_id = provider_data.get("order_id") or row["provider_reference"]
        payment_cards = provider_data.get("payment_cards")
        trans_status = provider_data.get("trans_status")
        error_code = provider_data.get("error_code")
        form_token = provider_data.get("form_token")
        raw_answer = provider_data.get("_raw_answer")

        bind.execute(
            sa.update(payments)
            .where(payments.c.id == row["id"])
            .values(
                payzen_trans_id=(str(trans_id) if trans_id is not None else None),
                payzen_order_id=(str(order_id) if order_id is not None else None),
                payzen_payment_method=(
                    str(payment_cards) if payment_cards is not None else None
                ),
                payzen_status=(str(trans_status) if trans_status is not None else None),
                payzen_error_code=(str(error_code) if error_code is not None else None),
                payzen_form_token=(str(form_token) if form_token is not None else None),
                payzen_data=(raw_answer if isinstance(raw_answer, dict) else None),
            )
        )
