"""avis clients : modération, achat vérifié, nom affiché

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-10-27 12:00:00.000000

Un avis n'est publié qu'une fois approuvé par la boutique. Les avis existants
(aucun écran ne les montrait) attendent la modération comme les nouveaux.
"""

import sqlalchemy as sa
from alembic import op

revision = "d4e5f6a7b8c9"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "reviews",
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="pending"
        ),
    )
    op.create_index("ix_reviews_status", "reviews", ["status"])
    op.add_column(
        "reviews",
        sa.Column(
            "verified_purchase",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column("reviews", sa.Column("author_name", sa.String(length=60)))
    op.add_column(
        "reviews", sa.Column("moderated_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "reviews",
        sa.Column(
            "moderated_by_id",
            sa.Uuid(),
            sa.ForeignKey("users.id"),
            nullable=True,
        ),
    )
    op.add_column(
        "reviews", sa.Column("moderation_note", sa.String(length=300), nullable=True)
    )
    # One review per customer and product: the storefront edits it in place.
    # Older duplicates (none expected) step aside first.
    op.execute(
        """
        UPDATE reviews SET is_active = false WHERE id IN (
            SELECT id FROM (
                SELECT id, row_number() OVER (
                    PARTITION BY user_id, product_id
                    ORDER BY created_at DESC NULLS LAST, id
                ) AS n
                FROM reviews WHERE is_active
            ) ranked WHERE n > 1
        )
        """
    )
    op.create_index(
        "ux_reviews_user_product_active",
        "reviews",
        ["user_id", "product_id"],
        unique=True,
        postgresql_where=sa.text("is_active"),
    )


def downgrade() -> None:
    op.drop_index("ux_reviews_user_product_active", table_name="reviews")
    op.drop_column("reviews", "moderation_note")
    op.drop_column("reviews", "moderated_by_id")
    op.drop_column("reviews", "moderated_at")
    op.drop_column("reviews", "author_name")
    op.drop_column("reviews", "verified_purchase")
    op.drop_index("ix_reviews_status", table_name="reviews")
    op.drop_column("reviews", "status")
