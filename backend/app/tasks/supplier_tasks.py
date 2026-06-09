"""
ARQ tasks for supplier synchronization.

One parameterized task per operation (``supplier_name`` is always the first
argument); the cron schedule iterates over every registered supplier.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any, cast
from uuid import uuid4

from arq import cron
from sqlmodel import and_, col, or_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.integrations.crud.supplier_sync import supplier_sync_log_crud
from app.features.integrations.models.supplier_sync import SyncStatus, SyncType
from app.features.integrations.services.supplier_data_normalization import (
    meets_sync_thresholds,
    normalize_supplier_snapshot,
)
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product, ProductUpdate
from app.features.product.services.pricing import (
    CurrencyRateMissing,
    convert_to_reference_currency,
)
from app.services.suppliers import all_adapters, get_adapter, has_supplier

logger = logging.getLogger(__name__)


def _now() -> datetime:
    """Execute now."""
    return datetime.now(timezone.utc)


async def sync_supplier_products_task(
    _ctx: dict[str, Any],
    supplier_name: str,
    categories: list[str] | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """ARQ task: synchronize the catalog of ``supplier_name`` into the database."""
    if not has_supplier(supplier_name):
        return {"status": "error", "message": f"Unknown supplier: {supplier_name}"}

    adapter = get_adapter(supplier_name)
    if not adapter.is_sync_enabled():
        logger.debug("%s sync is disabled in settings", supplier_name)
        return {"status": "disabled", "message": "Sync disabled in settings"}
    if not adapter.is_configured():
        logger.error("%s credentials not configured", supplier_name)
        return {"status": "error", "message": f"Missing {supplier_name} credentials"}

    sync_categories = list(categories or adapter.default_categories)
    logger.debug(
        "Starting %s product sync for categories: %s", supplier_name, sync_categories
    )

    try:
        async with AsyncSession(engine) as session:
            raw_job_id = _ctx.get("job_id")
            sync_log = await supplier_sync_log_crud.create_sync_log(
                session=session,
                supplier_name=supplier_name,
                sync_type=SyncType.PRODUCT_CATALOG,
                categories=sync_categories,
                job_id=str(raw_job_id) if raw_job_id else None,
            )
            await supplier_sync_log_crud.start_sync(
                session=session, sync_log_id=sync_log.id
            )

            sync_start = _now()
            try:
                orchestrator = SupplierSyncOrchestrator(adapter)
                stats = await orchestrator.sync_products_to_database(
                    session=session, categories=sync_categories
                )
            except Exception as e:
                await supplier_sync_log_crud.complete_sync(
                    session=session,
                    sync_log_id=sync_log.id,
                    status=SyncStatus.FAILED,
                    error_message=str(e),
                )
                raise

            sync_end = _now()
            duration = (sync_end - sync_start).total_seconds()
            await supplier_sync_log_crud.complete_sync(
                session=session,
                sync_log_id=sync_log.id,
                status=SyncStatus.SUCCESS,
                statistics=stats,
            )

            logger.debug(
                "%s sync completed successfully in %.2fs. Stats: %s",
                supplier_name,
                duration,
                stats,
            )
            return {
                "status": "success",
                "supplier_name": supplier_name,
                "sync_log_id": str(sync_log.id),
                "categories": sync_categories,
                "start_time": sync_start.isoformat(),
                "end_time": sync_end.isoformat(),
                "duration_seconds": duration,
                "statistics": stats,
            }

    except Exception as e:
        logger.error("%s product sync failed: %s", supplier_name, e)
        return {
            "status": "error",
            "supplier_name": supplier_name,
            "message": str(e),
            "categories": sync_categories,
            "timestamp": _now().isoformat(),
        }


async def sync_supplier_inventory_task(
    _ctx: dict[str, Any],
    supplier_name: str,
    skus: list[str] | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """ARQ task: refresh price & availability for ``supplier_name`` products."""
    if not has_supplier(supplier_name):
        return {"status": "error", "message": f"Unknown supplier: {supplier_name}"}

    adapter = get_adapter(supplier_name)
    if not adapter.is_sync_enabled():
        return {"status": "disabled", "message": "Sync disabled in settings"}
    if not adapter.is_configured():
        logger.error("%s credentials not configured", supplier_name)
        return {"status": "error", "message": f"Missing {supplier_name} credentials"}

    logger.debug(
        "Starting %s inventory sync for %s products",
        supplier_name,
        len(skus) if skus else "all",
    )

    try:
        async with AsyncSession(engine) as session:
            if not skus:
                one_hour_ago = _now() - timedelta(hours=1)
                # include_archived=True so we can also refresh (and potentially
                # re-activate) products previously marked is_active=False.
                # Admin-disabled products remain excluded from supplier inventory sync.
                result = await crud_product.read_multi(
                    session,
                    filter=and_(
                        Product.supplier_name == supplier_name,
                        col(Product.is_supplier_managed).is_(True),
                        col(Product.is_admin_active).is_(True),
                        or_(
                            col(Product.last_supplier_sync) <= one_hour_ago,
                            col(Product.last_supplier_sync).is_(None),
                        ),
                    ),
                    include_archived=True,
                )
                products = result.get("data", [])
                skus = [p.supplier_sku for p in products if p.supplier_sku]
                logger.info("Fetched %s SKUs for inventory update", len(skus))

            batch_size = adapter.price_batch_size
            total_updated = 0
            errors = 0
            # Cache FX rates within this sync run: currency_code → rate_to_reference (None = missing)
            _fx_rate_cache: dict[str, Decimal | None] = {}

            for i in range(0, len(skus), batch_size):
                batch_skus = skus[i : i + batch_size]
                try:
                    pricing = await adapter.fetch_price_and_availability(batch_skus)
                    for sku, data in pricing.items():
                        try:
                            product = await crud_product.get_by_supplier_sku(
                                session=session,
                                supplier_sku=sku,
                                supplier_name=supplier_name,
                                supplier_managed_only=True,
                            )
                            if not product:
                                logger.warning(
                                    "Product with SKU %s not found for %s",
                                    sku,
                                    supplier_name,
                                )
                                continue

                            if not getattr(product, "is_admin_active", True):
                                logger.info(
                                    "Skipping inventory sync for product %s (%s): is_admin_active=False",
                                    product.id,
                                    sku,
                                )
                                continue

                            snapshot = normalize_supplier_snapshot(
                                raw_price=data.price or 0,
                                raw_quantity=data.quantity or 0,
                                raw_currency=data.currency or "USD",
                            )

                            # Convert supplier price to the reference currency
                            # so that SUPPLIER_SYNC_MIN_PRICE is always compared
                            # in the same currency regardless of the supplier's
                            # invoice currency (USD, EUR, …).
                            # Rate is cached per currency to avoid one DB query per SKU.
                            src_currency = snapshot.supplier_price_currency
                            if src_currency not in _fx_rate_cache:
                                try:
                                    _, rate = await convert_to_reference_currency(
                                        session, Decimal("1"), src_currency
                                    )
                                    _fx_rate_cache[src_currency] = rate
                                except CurrencyRateMissing:
                                    logger.warning(
                                        "No CurrencyRate for %s — "
                                        "SUPPLIER_SYNC_MIN_PRICE check falls back to raw price for SKU %s",
                                        src_currency,
                                        sku,
                                    )
                                    _fx_rate_cache[src_currency] = None

                            cached_rate = _fx_rate_cache[src_currency]
                            price_in_xpf: Decimal | None = None
                            if cached_rate is not None:
                                price_in_xpf = (
                                    snapshot.supplier_price * cached_rate
                                ).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

                            await crud_product.update(
                                session=session,
                                id=product.id,
                                data=ProductUpdate(
                                    cost_amount=snapshot.supplier_price,
                                    cost_currency=snapshot.supplier_price_currency,
                                    supplier_price=snapshot.supplier_price,
                                    supplier_price_currency=snapshot.supplier_price_currency,
                                    supplier_quantity=snapshot.supplier_quantity,
                                    is_active=meets_sync_thresholds(
                                        snapshot, price_in_xpf=price_in_xpf
                                    ),
                                    last_supplier_sync=_now(),
                                ),
                                record=product,
                                user=None,
                            )
                            total_updated += 1
                        except Exception as e:  # noqa: BLE001
                            logger.error(
                                "Error updating product %s (%s): %s",
                                sku,
                                supplier_name,
                                e,
                            )
                            errors += 1
                    await session.commit()
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "Error updating inventory batch for %s: %s", supplier_name, e
                    )
                    errors += 1
                    await session.rollback()

            logger.debug(
                "%s inventory sync completed. Updated %s products",
                supplier_name,
                total_updated,
            )
            return {
                "status": "success",
                "supplier_name": supplier_name,
                "total_skus": len(skus),
                "updated": total_updated,
                "errors": errors,
                "timestamp": _now().isoformat(),
            }

    except Exception as e:
        logger.error("%s inventory sync failed: %s", supplier_name, e)
        return {
            "status": "error",
            "supplier_name": supplier_name,
            "message": str(e),
            "timestamp": _now().isoformat(),
        }


async def check_supplier_health_task(
    _ctx: dict[str, Any], supplier_name: str, **_kwargs: Any
) -> dict[str, Any]:
    """ARQ task: probe ``supplier_name`` API health/connectivity."""
    if not has_supplier(supplier_name):
        return {"status": "error", "message": f"Unknown supplier: {supplier_name}"}

    adapter = get_adapter(supplier_name)
    logger.debug("Checking %s API health", supplier_name)
    health = await adapter.health_check()
    return {
        "status": "healthy" if health.healthy else "unhealthy",
        "supplier_name": supplier_name,
        "configured": health.configured,
        "message": health.message,
        "details": health.details,
        "timestamp": _now().isoformat(),
    }


# -- cron scheduling ------------------------------------------------------

# arq's ``cron()`` cannot pass arguments to the scheduled coroutine, so we wrap
# each parameterized task in a tiny per-supplier closure.


def _bind_supplier(task: Any, supplier_name: str, label: str) -> Any:
    """Execute bind supplier."""

    async def _runner(ctx: dict[str, Any]) -> Any:
        """Execute runner."""
        return await task(ctx, supplier_name=supplier_name)

    _runner.__name__ = f"{supplier_name}_{label}"
    _runner.__qualname__ = _runner.__name__
    return _runner


def get_supplier_sync_cron_jobs() -> list[Any]:
    """Build cron jobs for every registered & sync-enabled supplier."""
    jobs: list[Any] = []
    for adapter in all_adapters():
        if not adapter.is_sync_enabled():
            continue
        name = adapter.name
        interval = int(adapter.sync_interval_hours())

        if interval > 0:
            jobs.append(
                cron(
                    _bind_supplier(sync_supplier_products_task, name, "product_sync"),
                    hour=set(range(0, 24, interval)),
                    minute=0,
                    second=0,
                    name=f"{name}_product_sync",
                )
            )
        else:
            logger.debug(
                "%s product sync cron disabled (sync_interval_hours=%s)",
                name,
                interval,
            )
        jobs.append(
            cron(
                _bind_supplier(sync_supplier_inventory_task, name, "inventory_sync"),
                hour=set(range(0, 24, 2)),
                minute=30,
                second=0,
                name=f"{name}_inventory_sync",
            )
        )
        jobs.append(
            cron(
                _bind_supplier(check_supplier_health_task, name, "api_health_check"),
                hour=6,
                minute=0,
                second=0,
                name=f"{name}_api_health_check",
            )
        )
    return jobs


# -- manual triggers ------------------------------------------------------


async def _enqueue_with_dedup(
    function: str,
    *,
    dedup_namespace: str,
    job_prefix: str,
    payload_key: list[str] | None,
    job_kwargs: dict[str, Any],
) -> str:
    """Execute enqueue with dedup."""
    from app.core.arq_worker import get_redis_pool

    redis = await get_redis_pool()

    key_material = json.dumps(sorted(payload_key) if payload_key else []).encode()
    dedup_key = f"{dedup_namespace}:{hashlib.md5(key_material).hexdigest()}"  # noqa: S324
    job_id = (
        f"{job_prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    )

    was_set = await redis.set(dedup_key, job_id.encode(), ex=10, nx=True)
    if not was_set:
        existing = await redis.get(dedup_key)
        logger.debug(
            "%s already queued/running: %s",
            function,
            existing.decode() if existing else "unknown",
        )
        return existing.decode() if existing else job_id

    job = await redis.enqueue_job(
        function,
        _job_id=job_id,
        _max_tries=1,  # manual jobs: no automatic retry
        **job_kwargs,
    )
    logger.info("Manual %s triggered with job ID: %s", function, job.job_id)
    return cast(str, job.job_id)


async def trigger_manual_sync(
    supplier_name: str, categories: list[str] | None = None
) -> str:
    """Queue a manual catalog sync for ``supplier_name``; returns the ARQ job ID."""
    return await _enqueue_with_dedup(
        "sync_supplier_products_task",
        dedup_namespace=f"manual_sync_dedup:{supplier_name}",
        job_prefix=f"manual_sync_{supplier_name}",
        payload_key=categories,
        job_kwargs={"supplier_name": supplier_name, "categories": categories},
    )


async def trigger_inventory_refresh(
    supplier_name: str, skus: list[str] | None = None
) -> str:
    """Queue a manual inventory refresh for ``supplier_name``; returns the ARQ job ID."""
    return await _enqueue_with_dedup(
        "sync_supplier_inventory_task",
        dedup_namespace=f"manual_inventory_dedup:{supplier_name}",
        job_prefix=f"manual_inventory_{supplier_name}",
        payload_key=skus,
        job_kwargs={"supplier_name": supplier_name, "skus": skus},
    )


# -- category backfill -------------------------------------------------------


async def backfill_product_categories_task(
    _ctx: dict[str, Any],
    batch_size: int = 200,
    **_kwargs: Any,
) -> dict[str, int]:
    """ARQ task: populate Product.category_id for products that have a
    supplier_subcategory but no category_id yet.

    Safe to run multiple times (idempotent). Commits per batch so a failure
    mid-run preserves already-processed rows.
    """
    from sqlmodel import col, select

    from app.features.product.crud.category import crud_category
    from app.features.product.models.product import Product

    stats = {"updated": 0, "categories_created": 0, "errors": 0}

    async with AsyncSession(engine) as session:
        while True:
            stmt = (
                select(Product)
                .where(
                    col(Product.supplier_subcategory).is_not(None),
                    col(Product.category_id).is_(None),
                    col(Product.is_active).is_(True),
                )
                .limit(batch_size)
            )
            result = await session.exec(stmt)
            batch = list(result.all())
            if not batch:
                break

            for product in batch:
                try:
                    if not product.supplier_subcategory:
                        continue
                    category, created = await crud_category.get_or_create_by_name(
                        session, name=product.supplier_subcategory
                    )
                    if created:
                        stats["categories_created"] += 1
                    product.category_id = category.id
                    session.add(product)
                    stats["updated"] += 1
                except Exception as e:  # noqa: BLE001
                    logger.error(
                        "Error backfilling category for product %s: %s", product.id, e
                    )
                    stats["errors"] += 1

            await session.commit()

    logger.info("Category backfill completed: %s", stats)
    return stats
