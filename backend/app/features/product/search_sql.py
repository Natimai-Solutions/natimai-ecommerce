"""Database objects the product search relies on.

``unaccent`` is only STABLE (its dictionary can change), so PostgreSQL refuses
it in an index expression. ``shop_unaccent`` pins the dictionary by its
schema-qualified name and is declared IMMUTABLE: the full-text index and the
search queries both wrap the text in it, so « ecran » finds « Écran ».

The migration ``c3d4e5f6a7b8`` creates the same objects; the integration
tests, which build the schema from the models, run :data:`SEARCH_SQL_SETUP`.
"""

from __future__ import annotations

#: Name of the immutable unaccent wrapper (SQL function).
UNACCENT_FUNCTION = "shop_unaccent"

UNACCENT_FUNCTION_DDL = f"""
CREATE OR REPLACE FUNCTION {UNACCENT_FUNCTION}(text) RETURNS text
LANGUAGE sql IMMUTABLE PARALLEL SAFE STRICT
AS $$ SELECT public.unaccent('public.unaccent'::regdictionary, $1) $$
"""

SEARCH_SQL_SETUP: tuple[str, ...] = (
    "CREATE EXTENSION IF NOT EXISTS pg_trgm",
    "CREATE EXTENSION IF NOT EXISTS unaccent",
    UNACCENT_FUNCTION_DDL,
)
