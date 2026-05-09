"""payments_amount_to_decimal

Revision ID: 7d4c2e1a9b30
Revises: 5c7b6e4a1f29
Create Date: 2026-05-08 18:00:00.000000

Aligns Phase B6: stores `payments.amount` and `payment_logs.amount` as
NUMERIC(12,2) (Decimal in the payment currency) instead of integer minor
units, so all monetary fields (product, order, payment) share the same
representation.

The conversion preserves existing data: zero-decimal currencies (XPF, JPY,
KRW) keep their integer value, others are divided by 100. `payment_logs`
inherits its currency from the parent `payments` row via an UPDATE join
(PostgreSQL forbids subqueries inside ALTER COLUMN ... USING).
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "7d4c2e1a9b30"
down_revision = "5c7b6e4a1f29"
branch_labels = None
depends_on = None


ZERO_DECIMAL_CURRENCIES_SQL = "('XPF', 'JPY', 'KRW')"


def upgrade():
    # 1) payments.amount: same-row CASE works inside USING.
    op.alter_column(
        "payments",
        "amount",
        existing_type=sa.Integer(),
        type_=sa.Numeric(precision=12, scale=2),
        existing_nullable=False,
        postgresql_using=(
            "CASE WHEN currency IN "
            f"{ZERO_DECIMAL_CURRENCIES_SQL} "
            "THEN amount::numeric "
            "ELSE amount::numeric / 100 END"
        ),
    )

    # 2) payment_logs.amount: needs the parent payment currency, so we
    #    materialise the converted value in a temporary column before
    #    swapping it in (subqueries are not allowed in ALTER ... USING).
    op.add_column(
        "payment_logs",
        sa.Column(
            "amount_decimal",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
    )
    op.execute(
        "UPDATE payment_logs pl "
        "SET amount_decimal = CASE "
        f"WHEN p.currency IN {ZERO_DECIMAL_CURRENCIES_SQL} "
        "THEN pl.amount::numeric "
        "ELSE pl.amount::numeric / 100 END "
        "FROM payments p WHERE p.id = pl.payment_id"
    )
    op.alter_column("payment_logs", "amount_decimal", nullable=False)
    op.drop_column("payment_logs", "amount")
    op.alter_column(
        "payment_logs",
        "amount_decimal",
        new_column_name="amount",
    )


def downgrade():
    # Symmetrical: payment_logs first, then payments.
    op.add_column(
        "payment_logs",
        sa.Column("amount_int", sa.Integer(), nullable=True),
    )
    op.execute(
        "UPDATE payment_logs pl "
        "SET amount_int = CASE "
        f"WHEN p.currency IN {ZERO_DECIMAL_CURRENCIES_SQL} "
        "THEN (pl.amount)::integer "
        "ELSE (pl.amount * 100)::integer END "
        "FROM payments p WHERE p.id = pl.payment_id"
    )
    op.alter_column("payment_logs", "amount_int", nullable=False)
    op.drop_column("payment_logs", "amount")
    op.alter_column(
        "payment_logs",
        "amount_int",
        new_column_name="amount",
    )

    op.alter_column(
        "payments",
        "amount",
        existing_type=sa.Numeric(precision=12, scale=2),
        type_=sa.Integer(),
        existing_nullable=False,
        postgresql_using=(
            "CASE WHEN currency IN "
            f"{ZERO_DECIMAL_CURRENCIES_SQL} "
            "THEN (amount)::integer "
            "ELSE (amount * 100)::integer END"
        ),
    )
