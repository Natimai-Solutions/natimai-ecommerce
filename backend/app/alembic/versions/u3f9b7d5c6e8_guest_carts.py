"""panier invité serveur (R8 / U9) : carts.user_id nullable, guest_token, guest_email

Revision ID: u3f9b7d5c6e8
Revises: t2e8a6c4b5d7
Create Date: 2026-10-02 21:00:00.000000
"""

import sqlalchemy as sa
import sqlmodel
from alembic import op

revision = "u3f9b7d5c6e8"
down_revision = "t2e8a6c4b5d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("carts", "user_id", existing_type=sa.Uuid(), nullable=True)
    op.add_column(
        "carts",
        sa.Column(
            "guest_token", sqlmodel.sql.sqltypes.AutoString(length=128), nullable=True
        ),
    )
    op.add_column(
        "carts",
        sa.Column(
            "guest_email", sqlmodel.sql.sqltypes.AutoString(length=255), nullable=True
        ),
    )
    op.create_index(
        "ix_carts_guest_token", "carts", ["guest_token"], unique=True
    )


def downgrade() -> None:
    op.drop_index("ix_carts_guest_token", table_name="carts")
    op.drop_column("carts", "guest_email")
    op.drop_column("carts", "guest_token")
    # Visitors' carts have no owner: they must go before the column tightens.
    op.execute("DELETE FROM cart_items WHERE cart_id IN (SELECT id FROM carts WHERE user_id IS NULL)")
    op.execute("DELETE FROM carts WHERE user_id IS NULL")
    op.alter_column("carts", "user_id", existing_type=sa.Uuid(), nullable=False)
