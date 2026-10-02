"""traduction du contenu (R9 / T3) : colonne translations, pages <slug>-en, index FTS

Revision ID: q8b5d3f1e2a4
Revises: d6e9f3a7b2c4
Create Date: 2026-10-02 03:00:00.000000

Une colonne JSONB ``translations`` ({"en": {"name": "…", "_source": "…"}})
sur les produits, catégories, pages du site, blocs d'accueil et définitions
de caractéristiques ; les colonnes existantes restent la langue par défaut.

Les pages ``<slug>-en`` (contournement R7) deviennent la traduction anglaise
de la page ``<slug>`` quand celle-ci existe, puis sont supprimées.

L'index plein texte des produits indexe aussi le nom et la description
anglais : l'expression doit rester identique à celle de
``ProductCrud.search_products``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "q8b5d3f1e2a4"
down_revision = "d6e9f3a7b2c4"
branch_labels = None
depends_on = None

_TABLES = (
    "products",
    "categories",
    "content_pages",
    "homepage_blocks",
    "spec_definitions",
)

_FTS_EXPRESSION = """
    to_tsvector('simple',
        coalesce(name, '') || ' ' ||
        coalesce(description, '') || ' ' ||
        coalesce(manufacturer, '') || ' ' ||
        coalesce(vendor_part_number, '') || ' ' ||
        coalesce(translations -> 'en' ->> 'name', '') || ' ' ||
        coalesce(translations -> 'en' ->> 'description', '')
    )
"""

_FTS_EXPRESSION_BEFORE = """
    to_tsvector('simple',
        coalesce(name, '') || ' ' ||
        coalesce(description, '') || ' ' ||
        coalesce(manufacturer, '') || ' ' ||
        coalesce(vendor_part_number, '')
    )
"""


def upgrade() -> None:
    for table in _TABLES:
        op.add_column(
            table,
            sa.Column(
                "translations",
                postgresql.JSONB(astext_type=sa.Text()),
                nullable=False,
                server_default=sa.text("'{}'::jsonb"),
            ),
        )

    # ``<slug>-en`` → translation of ``<slug>`` (same digest rule as the API:
    # the fingerprint is recomputed by the back-office on the next save, so the
    # translation first reads as « à relire », which is honest).
    op.execute(
        """
        UPDATE content_pages AS page
        SET translations = page.translations || jsonb_build_object(
            'en', jsonb_build_object(
                'title', en.title,
                'body_html', en.body_html,
                '_source', 'migrated'
            )
        )
        FROM content_pages AS en
        WHERE en.slug = page.slug || '-en'
          AND en.is_active IS TRUE
          AND page.is_active IS TRUE
        """
    )
    op.execute(
        """
        DELETE FROM content_pages AS en
        USING content_pages AS page
        WHERE en.slug = page.slug || '-en'
          AND en.is_active IS TRUE
          AND page.is_active IS TRUE
        """
    )

    op.execute("DROP INDEX IF EXISTS ix_products_search_fts")
    op.execute(
        f"CREATE INDEX ix_products_search_fts ON products USING GIN ({_FTS_EXPRESSION})"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_products_search_fts")
    op.execute(
        "CREATE INDEX ix_products_search_fts ON products "
        f"USING GIN ({_FTS_EXPRESSION_BEFORE})"
    )
    for table in reversed(_TABLES):
        op.drop_column(table, "translations")
