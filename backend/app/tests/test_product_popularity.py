"""Unit: the view counter statement and the ranking query (no database)."""

from __future__ import annotations

import uuid
from datetime import date
from typing import Any

from sqlalchemy.dialects import postgresql

from app.features.product.services.popularity import (
    popular_products_statement,
    view_upsert_statement,
)


def _sql(statement: Any) -> str:
    compiled = statement.compile(  # type: ignore[no-untyped-call]
        dialect=postgresql.dialect(), compile_kwargs={"literal_binds": True}
    )
    return str(compiled)


def test_a_view_is_one_upsert_that_increments_the_day_counter() -> None:
    sql = _sql(view_upsert_statement(uuid.uuid4(), date(2026, 9, 10)))
    assert "INSERT INTO product_view_daily" in sql
    assert "ON CONFLICT (product_id, day) DO UPDATE" in sql
    assert "SET views = (product_view_daily.views + 1)" in sql


def test_ranking_sums_views_over_the_window_and_limits() -> None:
    sql = _sql(popular_products_statement(conditions=[], days=30, limit=8))
    assert "sum(product_view_daily.views) AS total_views" in sql
    assert "product_view_daily.day >= " in sql
    assert "ORDER BY total_views DESC" in sql
    assert "LIMIT 8" in sql
