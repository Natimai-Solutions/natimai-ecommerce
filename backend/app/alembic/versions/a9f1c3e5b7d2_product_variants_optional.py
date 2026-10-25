"""déclinaisons optionnelles : le produit de base reste commandable

Revision ID: a9f1c3e5b7d2
Revises: z8e4a2c0b1d3
Create Date: 2026-10-06 10:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "a9f1c3e5b7d2"
down_revision = "z8e4a2c0b1d3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Existing parents keep today's rule: a variant must be chosen.
    op.add_column(
        "products",
        sa.Column(
            "variants_optional",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )


def downgrade() -> None:
    op.drop_column("products", "variants_optional")
