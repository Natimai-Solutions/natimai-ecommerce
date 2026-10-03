"""cartes cadeaux et bons d'achat (R8 / confort) : table gift_cards, products.gift_card_amount

Revision ID: v4a0c8e6d7f9
Revises: u3f9b7d5c6e8
Create Date: 2026-10-03 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op

revision = "v4a0c8e6d7f9"
down_revision = "u3f9b7d5c6e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "gift_cards",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=20), nullable=False),
        sa.Column("amount", sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column("currency", sa.String(length=8), nullable=False),
        sa.Column("recipient_email", sa.String(length=255), nullable=True),
        sa.Column("note", sa.String(length=500), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("order_id", sa.Uuid(), nullable=True),
        sa.Column("code", sa.String(length=32), nullable=False),
        sa.Column("redeemed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("redeemed_by_id", sa.Uuid(), nullable=True),
        sa.Column("store_credit_entry_id", sa.Uuid(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("is_admin_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_id", sa.Uuid(), nullable=True),
        sa.Column("modify_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("modify_by_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(["order_id"], ["orders.id"]),
        sa.ForeignKeyConstraint(["redeemed_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["store_credit_entry_id"], ["store_credit_entries.id"]),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["modify_by_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_gift_cards_id", "gift_cards", ["id"])
    op.create_index("ix_gift_cards_code", "gift_cards", ["code"], unique=True)
    op.create_index("ix_gift_cards_order_id", "gift_cards", ["order_id"])
    op.create_index("ix_gift_cards_redeemed_by_id", "gift_cards", ["redeemed_by_id"])
    op.add_column(
        "products",
        sa.Column("gift_card_amount", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("products", "gift_card_amount")
    op.drop_index("ix_gift_cards_redeemed_by_id", table_name="gift_cards")
    op.drop_index("ix_gift_cards_order_id", table_name="gift_cards")
    op.drop_index("ix_gift_cards_code", table_name="gift_cards")
    op.drop_index("ix_gift_cards_id", table_name="gift_cards")
    op.drop_table("gift_cards")
