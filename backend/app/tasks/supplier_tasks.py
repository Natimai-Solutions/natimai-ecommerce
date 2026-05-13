"""
ARQ tasks for supplier synchronization.

One parameterized task per operation (``supplier_name`` is always the first
argument); the cron schedule iterates over every registered supplier.
"""

import hashlib
import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, cast
from uuid import uuid4

from arq import cron
from sqlmodel import and_, col, or_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.integrations.crud.supplier_sync import supplier_sync_log_crud
from app.features.integrations.models.supplier_sync import SyncStatus, SyncType
from app.features.integrations.services.supplier_data_normalization import (
    normalize_supplier_snapshot,
)
from app.features.integrations.services.supplier_sync_orchestrator import (
    SupplierSyncOrchestrator,
)
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product, ProductUpdate
from app.services.suppliers import all_adapters, get_adapter, has_supplier

logger = logging.getLogger(__name__)


def _now() -> datetime:
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
                result = await crud_product.read_multi(
                    session,
                    filter=and_(
                        Product.supplier_name == supplier_name,
                        col(Product.is_supplier_managed).is_(True),
                        or_(
                            col(Product.last_supplier_sync) <= one_hour_ago,
                            col(Product.last_supplier_sync).is_(None),
                        ),
                    ),
                )
                products = result.get("data", [])
                skus = [p.supplier_sku for p in products if p.supplier_sku]
                logger.info("Fetched %s SKUs for inventory update", len(skus))

            batch_size = adapter.price_batch_size
            total_updated = 0
            errors = 0

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

                            snapshot = normalize_supplier_snapshot(
                                raw_price=data.price or 0,
                                raw_quantity=data.quantity or 0,
                                raw_currency=data.currency or "USD",
                            )
                            await crud_product.update(
                                session=session,
                                id=product.id,
                                data=ProductUpdate(
                                    supplier_price=snapshot.supplier_price,
                                    supplier_price_currency=snapshot.supplier_price_currency,
                                    base_price=snapshot.base_price,
                                    supplier_quantity=snapshot.supplier_quantity,
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
    async def _runner(ctx: dict[str, Any]) -> Any:
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
