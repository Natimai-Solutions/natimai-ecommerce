"""recherche sans accents : shop_unaccent et index plein texte

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-10-27 09:00:00.000000

« ecran » ne trouvait pas « Écran » : le texte indexé et la requête passent
désormais par ``shop_unaccent`` (unaccent figé, IMMUTABLE, donc indexable).
L'expression de l'index doit rester celle de ``ProductCrud._search_document``.
"""

from alembic import op

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None

_TEXT = """
        coalesce(name, '') || ' ' ||
        coalesce(description, '') || ' ' ||
        coalesce(manufacturer, '') || ' ' ||
        coalesce(vendor_part_number, '') || ' ' ||
        coalesce(translations -> 'en' ->> 'name', '') || ' ' ||
        coalesce(translations -> 'en' ->> 'description', '')
"""


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS unaccent")
    op.execute(
        """
        CREATE OR REPLACE FUNCTION shop_unaccent(text) RETURNS text
        LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
        AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
        """
    )
    op.execute("DROP INDEX IF EXISTS ix_products_search_fts")
    op.execute(
        "CREATE INDEX ix_products_search_fts ON products USING GIN "
        f"(to_tsvector('simple', shop_unaccent({_TEXT})))"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_search_fts")
    op.execute(
        "CREATE INDEX ix_products_search_fts ON products USING GIN "
        f"(to_tsvector('simple', {_TEXT}))"
    )
    op.execute("DROP FUNCTION IF EXISTS shop_unaccent(text)")
