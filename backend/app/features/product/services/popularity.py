"""Record product views and rank products by views over a window (M1)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.models.product import Product
from app.features.product.models.product_view import ProductViewDaily

#: Ranking window and page size defaults for the storefront.
DEFAULT_WINDOW_DAYS = 30
DEFAULT_LIMIT = 8
MAX_WINDOW_DAYS = 365
MAX_LIMIT = 50


def _today() -> date:
    return datetime.now(timezone.utc).date()


def view_upsert_statement(product_id: uuid.UUID, day: date | None = None) -> Any:
    """``INSERT … ON CONFLICT (product_id, day) DO UPDATE views = views + 1``.

    One statement, no read-modify-write: concurrent page loads never lose a
    count and never race on the unique key.
    """
    statement = pg_insert(ProductViewDaily).values(
        id=uuid.uuid4(), product_id=product_id, day=day or _today(), views=1
    )
    return statement.on_conflict_do_update(
        index_elements=["product_id", "day"],
        set_={"views": ProductViewDaily.views + 1},
    )


async def record_product_view(
    session: AsyncSession, *, product_id: uuid.UUID, commit: bool = True
) -> None:
    """Count one view of ``product_id`` today."""
    await session.execute(view_upsert_statement(product_id))
    if commit:
        await session.commit()


def popular_products_statement(
    *,
    conditions: list[Any],
    days: int = DEFAULT_WINDOW_DAYS,
    limit: int = DEFAULT_LIMIT,
) -> Any:
    """Products ranked by views over the last ``days`` days.

    ``conditions`` restrict to what the storefront may show (active,
    publishable…) so a hidden product never ranks. Ties break on the most
    recent product so the list stays stable between runs.
    """
    since = _today() - timedelta(days=max(1, days) - 1)
    total_views = func.sum(col(ProductViewDaily.views)).label("total_views")
    return (
        select(Product, total_views)
        .join(ProductViewDaily, col(ProductViewDaily.product_id) == col(Product.id))
        .where(col(ProductViewDaily.day) >= since, *conditions)
        .group_by(col(Product.id))
        .order_by(total_views.desc(), col(Product.created_at).desc())
        .limit(limit)
    )


async def popular_products(
    session: AsyncSession,
    *,
    conditions: list[Any],
    days: int = DEFAULT_WINDOW_DAYS,
    limit: int = DEFAULT_LIMIT,
) -> list[Product]:
    """Ranked products (see :func:`popular_products_statement`)."""
    rows = await session.exec(
        popular_products_statement(conditions=conditions, days=days, limit=limit)
    )
    return [row[0] for row in rows.all()]
