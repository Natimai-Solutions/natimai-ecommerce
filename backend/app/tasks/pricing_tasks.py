"""Materialized storefront prices: refresh task, scheduler and admin triggers.

``products.sale_price_cached`` is what the storefront search filters, sorts
and returns. The product CRUD keeps it right on every product write; this
module covers the other way a price changes — a *parameter* moved:

* a tax rate, a currency rate, a category margin or customs default edited in
  the admin → the route calls :func:`schedule_price_refresh` (whole catalog
  or one category), deduplicated through Redis;
* a validity date reached (``valid_from`` / ``valid_until`` on taxes and
  rates change the price at midnight without any write) → nightly cron.

The refresh itself is one :class:`PricingContext` and in-memory pricing,
committed by batches, so a full catalog costs a handful of queries.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from arq import cron
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product
from app.features.product.services.category_tree import (
    product_in_category_condition,
)
from app.features.product.services.pricing import PricingContext
from app.features.product.services.variants import refresh_all_parents
from app.tasks.enqueue import enqueue_with_dedup

logger = logging.getLogger(__name__)

BATCH_SIZE = 500


def _now() -> datetime:
    return datetime.now(UTC)


async def refresh_sale_prices(
    session: AsyncSession,
    *,
    category_id: uuid.UUID | None = None,
    product_ids: list[uuid.UUID] | None = None,
    batch_size: int = BATCH_SIZE,
    reason: str = "refresh",
) -> dict[str, int]:
    """Recompute ``sale_price_cached`` for the selected products, by batches.

    Every product is refreshed, published or not: an admin who fixes the
    customs rate of a category expects the list price to be right the moment
    the products become publishable. ``reason`` is what the price journal
    records for each product whose price moved.
    """
    id_statement = select(col(Product.id)).order_by(col(Product.id))
    if category_id is not None:
        # A default set on « Réseau » reprices the WiFi access points too.
        id_statement = id_statement.where(product_in_category_condition(category_id))
    if product_ids:
        id_statement = id_statement.where(col(Product.id).in_(product_ids))
    ids = list((await session.exec(id_statement)).all())

    context = await PricingContext.load(session)
    stats = {"total": len(ids), "priced": 0, "unpriced": 0, "batches": 0}
    for start in range(0, len(ids), batch_size):
        chunk = ids[start : start + batch_size]
        products = list(
            (
                await session.exec(select(Product).where(col(Product.id).in_(chunk)))
            ).all()
        )
        priced = await crud_product.refresh_cached_prices(
            session, products, context=context, reason=reason
        )
        stats["priced"] += priced
        stats["unpriced"] += len(products) - priced
        stats["batches"] += 1
        await session.commit()
    # Parents show « à partir de » = their cheapest variant: roll them up
    # once the variants carry their fresh price.
    stats["parents"] = await refresh_all_parents(session)
    await session.commit()
    return stats


async def refresh_sale_prices_task(
    _ctx: dict[str, Any],
    category_id: str | None = None,
    product_ids: list[str] | None = None,
    reason: str | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """ARQ task: refresh the materialized list prices (whole catalog by default)."""
    started = _now()
    try:
        async with AsyncSession(engine) as session:
            stats = await refresh_sale_prices(
                session,
                category_id=uuid.UUID(category_id) if category_id else None,
                product_ids=[uuid.UUID(p) for p in product_ids]
                if product_ids
                else None,
                reason=reason or "scheduled",
            )
    except Exception as exc:  # noqa: BLE001
        logger.error("Sale price refresh failed (%s): %s", reason, exc)
        return {"status": "error", "message": str(exc), "reason": reason}
    logger.info(
        "Sale prices refreshed (%s) in %.1fs: %s",
        reason or "scheduled",
        (_now() - started).total_seconds(),
        stats,
    )
    return {
        "status": "success",
        "reason": reason,
        "category_id": category_id,
        "timestamp": _now().isoformat(),
        **stats,
    }


async def scheduled_sale_price_refresh_task(
    _ctx: dict[str, Any], *_args: Any, **_kwargs: Any
) -> dict[str, Any]:
    """Nightly tick: tax and currency validity dates roll over at midnight."""
    return await refresh_sale_prices_task(_ctx, reason="nightly")


def get_pricing_cron_jobs() -> list[Any]:
    """Build the nightly refresh (00:05, after the date has changed everywhere)."""
    return [
        cron(
            scheduled_sale_price_refresh_task,  # type: ignore[arg-type]
            hour=0,
            minute=5,
            second=0,
            name="sale_price_nightly_refresh",
        )
    ]


async def trigger_price_refresh(
    *, reason: str, category_id: uuid.UUID | None = None
) -> str:
    """Queue a refresh; a second identical trigger within 10 s is absorbed."""
    scope = str(category_id) if category_id else "all"
    return await enqueue_with_dedup(
        "refresh_sale_prices_task",
        dedup_namespace="price_refresh_dedup",
        job_prefix="price_refresh",
        payload_key=[scope],
        job_kwargs={
            "category_id": str(category_id) if category_id else None,
            "reason": reason,
        },
    )


async def schedule_price_refresh(
    *, reason: str, category_id: uuid.UUID | None = None
) -> str | None:
    """Best-effort trigger for admin routes: a queue outage never fails the edit.

    The nightly cron and the write hooks catch up; the warning tells the
    operator the listing may lag until then.
    """
    try:
        return await trigger_price_refresh(reason=reason, category_id=category_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Could not queue the sale price refresh (%s): %s — prices refresh "
            "on the next product write or tonight",
            reason,
            exc,
        )
        return None
