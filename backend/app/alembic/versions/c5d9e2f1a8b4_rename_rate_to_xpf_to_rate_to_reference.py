"""rename currency_rates.rate_to_xpf to rate_to_reference

Revision ID: c5d9e2f1a8b4
Revises: f2a4b8c1d9e3
Create Date: 2026-05-28 00:00:00.000000

De-localises the reference (pivot) currency: the column no longer hardcodes
"xpf" in its name. Pure rename — no data/semantics change. See
docs/development/PLAN_DEPLOIEMENT_PAR_PHASE.md →
"Devise de référence (pivot) paramétrable".
"""

from alembic import op

revision = "c5d9e2f1a8b4"
down_revision = "f2a4b8c1d9e3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "currency_rates",
        "rate_to_xpf",
        new_column_name="rate_to_reference",
    )


def downgrade() -> None:
    op.alter_column(
        "currency_rates",
        "rate_to_reference",
        new_column_name="rate_to_xpf",
    )
