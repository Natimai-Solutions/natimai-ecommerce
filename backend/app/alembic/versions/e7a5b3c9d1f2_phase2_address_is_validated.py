"""phase2_address_is_validated

Revision ID: e7a5b3c9d1f2
Revises: d6f4a2e8b1c3
Create Date: 2026-06-08

Adds is_validated column to addresses table.
Existing rows default to False (not yet validated).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "e7a5b3c9d1f2"
down_revision: str | None = "d6f4a2e8b1c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "addresses",
        sa.Column(
            "is_validated",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )


def downgrade() -> None:
    op.drop_column("addresses", "is_validated")
