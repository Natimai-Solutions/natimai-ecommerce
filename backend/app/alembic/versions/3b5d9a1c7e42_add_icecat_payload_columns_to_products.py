"""add icecat payload columns to products

Revision ID: 3b5d9a1c7e42
Revises: 2d7f4b8c9e11
Create Date: 2026-05-18 11:30:00.000000

"""

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = "3b5d9a1c7e42"
down_revision = "2d7f4b8c9e11"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products",
        sa.Column("technical_specifications", sa.JSON(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("features", sa.JSON(), nullable=True),
    )
    op.add_column(
        "products",
        sa.Column("icecat_images", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "icecat_images")
    op.drop_column("products", "features")
    op.drop_column("products", "technical_specifications")
