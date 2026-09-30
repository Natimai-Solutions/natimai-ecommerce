"""import en brouillon : Product.is_draft, Supplier.import_as_draft

Revision ID: m4d1f7b2c8e9
Revises: l3c9e6a1b4f7
Create Date: 2026-09-26 20:00:00.000000

"""

import sqlalchemy as sa
from alembic import op

revision = "m4d1f7b2c8e9"
down_revision = "l3c9e6a1b4f7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column(
            "is_draft", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.create_index(op.f("ix_products_is_draft"), "products", ["is_draft"])
    op.add_column(
        "suppliers",
        sa.Column(
            "import_as_draft",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )


def downgrade() -> None:
    op.drop_column("suppliers", "import_as_draft")
    op.drop_index(op.f("ix_products_is_draft"), table_name="products")
    op.drop_column("products", "is_draft")
