"""Phase 1: GIN FTS index + pg_trgm for product text search

Revision ID: f2a4b8c1d9e3
Revises: e3b7a1c9d5f2
Create Date: 2026-05-22 14:00:00.000000

Adds two indexes on the products table:
- ix_products_search_fts  : GIN on to_tsvector('simple', coalesce(...) || ' ' || ...)
                            Used by plainto_tsquery FTS queries.
- ix_products_name_trgm   : GIN trgm on name
                            Speeds up ILIKE '%...%' fallback on name.

Extensions required: pg_trgm (bundled with PostgreSQL contrib).

Note: concat_ws() is STABLE (not IMMUTABLE) so PostgreSQL rejects it in index
expressions. The `||` operator on text is IMMUTABLE — search_products() must use
the same expression for the GIN index to be picked up.
"""

from alembic import op

revision = "f2a4b8c1d9e3"
down_revision = "e3b7a1c9d5f2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    # GIN FTS index — expression must exactly match what search_products() sends.
    op.execute(
        """
        CREATE INDEX ix_products_search_fts ON products
        USING GIN (
            to_tsvector('simple',
                coalesce(name, '') || ' ' ||
                coalesce(description, '') || ' ' ||
                coalesce(manufacturer, '') || ' ' ||
                coalesce(vendor_part_number, '')
            )
        )
        """
    )

    # trgm index on name: accelerates ILIKE and pg_trgm similarity on product names.
    op.execute(
        """
        CREATE INDEX ix_products_name_trgm ON products
        USING GIN (name gin_trgm_ops)
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_name_trgm")
    op.execute("DROP INDEX IF EXISTS ix_products_search_fts")
