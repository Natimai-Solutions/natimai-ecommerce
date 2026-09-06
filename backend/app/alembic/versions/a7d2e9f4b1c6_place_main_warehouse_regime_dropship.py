"""main warehouse, origin customs regime and dropshipping on places

Revision ID: a7d2e9f4b1c6
Revises: f3c8d5e2b7a4
Create Date: 2026-09-05 12:00:00.000000

Three logistics facts move from code heuristics into the database:
  - is_main_warehouse : the one place supplier goods converge to (partial
    unique index — at most one true row)
  - customs_regime    : origin-place override ('domestic' | 'import'),
    null = derived from the country vs the main warehouse
  - dropship_enabled  : supplier ships straight to the customer
"""

import sqlalchemy as sa
from alembic import op

revision = "a7d2e9f4b1c6"
down_revision = "f3c8d5e2b7a4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "places",
        sa.Column(
            "is_main_warehouse",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "places",
        sa.Column("customs_regime", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "places",
        sa.Column(
            "dropship_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.create_index(
        "ix_places_is_main_warehouse", "places", ["is_main_warehouse"], unique=False
    )
    op.create_index(
        "uq_places_single_main_warehouse",
        "places",
        ["is_main_warehouse"],
        unique=True,
        postgresql_where=sa.text("is_main_warehouse"),
    )


def downgrade() -> None:
    op.drop_index("uq_places_single_main_warehouse", table_name="places")
    op.drop_index("ix_places_is_main_warehouse", table_name="places")
    op.drop_column("places", "dropship_enabled")
    op.drop_column("places", "customs_regime")
    op.drop_column("places", "is_main_warehouse")
