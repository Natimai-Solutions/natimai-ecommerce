"""
ARQ tasks for supplier synchronization.

One parameterized task per operation (``supplier_name`` is always the first
argument). Suppliers live in the database (``suppliers`` table): the cron
schedule is therefore not one job per supplier baked in at worker start, but
three *scheduler ticks* that read the table when they fire and enqueue one job
per API-backed supplier that is due. Adding, pausing or re-cadencing a
supplier in the admin takes effect at the next tick — no worker restart.
"""

import logging
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from arq import cron
from sqlmodel import and_, col, or_
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
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
from app.services.suppliers import api_suppliers, resolve_adapter
from app.services.suppliers.base import SupplierAdapter
from app.tasks.enqueue import enqueue_with_dedup

logger = logging.getLogger(__name__)

#: Cadence of the price & availability refresh for every API supplier.
INVENTORY_SYNC_EVERY_HOURS = 2


def _as_utc(value: datetime) -> datetime:
    """Read a stored timestamp as UTC-aware (the column is naive in Postgres)."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _now() -> datetime:
    """Execute now."""
    return datetime.now(timezone.utc)


async def _load_adapter(
    session: AsyncSession, supplier_name: str
) -> SupplierAdapter | dict[str, Any]:
    """Resolve the adapter for a task, or the error payload to return instead."""
    adapter = await resolve_adapter(session, supplier_name)
    if adapter is None:
        return {
            "status": "error",
            "message": f"Unknown or non-API supplier: {supplier_name}",
        }
    if not adapter.is_sync_enabled():
        logger.debug("%s sync is disabled", supplier_name)
        return {"status": "disabled", "message": "Sync disabled for this supplier"}
    if not adapter.is_configured():
        logger.error("%s credentials not configured", supplier_name)
        return {"status": "error", "message": f"Missing {supplier_name} credentials"}
    return adapter


async def sync_supplier_products_task(
    _ctx: dict[str, Any],
    supplier_name: str,
    categories: list[str] | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """ARQ task: synchronize the catalog of ``supplier_name`` into the database."""
    sync_categories: list[str] = list(categories or [])
    try:
        async with AsyncSession(engine) as session:
            loaded = await _load_adapter(session, supplier_name)
            if isinstance(loaded, dict):
                return loaded
            adapter = loaded

            sync_categories = list(categories or adapter.default_categories)
            logger.debug(
                "Starting %s product sync for categories: %s",
                supplier_name,
                sync_categories,
            )

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


async def _handle_missing_skus(
    session: AsyncSession,
    *,
    supplier_name: str,
    batch_skus: list[str],
    returned_skus: set[str],
) -> tuple[int, int]:
    """Track SKUs the supplier stopped returning, and delist the persistent ones.

    A SKU absent from a price & availability response is *not* deactivated on
    the spot: a transient supplier fault would otherwise wipe the catalog. The
    first absence stamps ``supplier_missing_since``; the product is only
    deactivated once the gap exceeds ``SUPPLIER_DELISTING_GRACE_HOURS``.

    Returns ``(newly_flagged, delisted)``.
    """
    missing = [sku for sku in batch_skus if sku not in returned_skus]
    if not missing:
        return 0, 0

    # An entirely empty response for a full batch is an API problem, not fifty
    # simultaneous delistings. Refuse to flag anything on that signal.
    if not returned_skus:
        logger.warning(
            "%s returned no pricing at all for a batch of %d SKUs — "
            "treating as a supplier fault, not a delisting",
            supplier_name,
            len(batch_skus),
        )
        return 0, 0

    grace_hours = int(settings.SUPPLIER_DELISTING_GRACE_HOURS)
    now = _now()
    cutoff = now - timedelta(hours=grace_hours) if grace_hours > 0 else None

    flagged = 0
    delisted = 0
    for sku in missing:
        product = await crud_product.get_by_supplier_sku(
            session=session,
            supplier_sku=sku,
            supplier_name=supplier_name,
            supplier_managed_only=True,
        )
        if product is None or not getattr(product, "is_admin_active", True):
            continue

        missing_since = product.supplier_missing_since
        if missing_since is None:
            await crud_product.update(
                session=session,
                id=product.id,
                data=ProductUpdate(supplier_missing_since=now),
                record=product,
                user=None,
            )
            flagged += 1
            logger.info(
                "%s no longer returns SKU %s — flagged, delisting in %dh if it "
                "does not come back",
                supplier_name,
                sku,
                grace_hours,
            )
            continue

        if cutoff is None or _as_utc(missing_since) > cutoff or not product.is_active:
            continue

        await crud_product.update(
            session=session,
            id=product.id,
            data=ProductUpdate(is_active=False),
            record=product,
            user=None,
        )
        delisted += 1
        logger.warning(
            "Delisting product %s (SKU %s): absent from %s since %s",
            product.id,
            sku,
            supplier_name,
            missing_since.isoformat(),
        )

    return flagged, delisted


async def sync_supplier_inventory_task(
    _ctx: dict[str, Any],
    supplier_name: str,
    skus: list[str] | None = None,
    **_kwargs: Any,
) -> dict[str, Any]:
    """ARQ task: refresh price & availability for ``supplier_name`` products."""
    logger.debug(
        "Starting %s inventory sync for %s products",
        supplier_name,
        len(skus) if skus else "all",
    )

    try:
        async with AsyncSession(engine) as session:
            loaded = await _load_adapter(session, supplier_name)
            if isinstance(loaded, dict):
                return loaded
            adapter = loaded

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
            total_flagged = 0
            total_delisted = 0
            errors = 0
            # Cache FX rates within this sync run: currency_code → rate_to_reference (None = missing)
            _fx_rate_cache: dict[str, Decimal | None] = {}
            fallback_currency = getattr(adapter, "price_currency", None) or "USD"

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
                                raw_currency=data.currency or fallback_currency,
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
                                    # The SKU answered: any pending delisting
                                    # countdown is void.
                                    supplier_missing_since=None,
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

                    flagged, delisted = await _handle_missing_skus(
                        session,
                        supplier_name=supplier_name,
                        batch_skus=batch_skus,
                        returned_skus=set(pricing),
                    )
                    total_flagged += flagged
                    total_delisted += delisted
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
                "flagged_missing": total_flagged,
                "delisted": total_delisted,
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
    async with AsyncSession(engine) as session:
        adapter = await resolve_adapter(session, supplier_name)
    if adapter is None:
        return {
            "status": "error",
            "message": f"Unknown or non-API supplier: {supplier_name}",
        }
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


# -- scheduler ticks ---------------------------------------------------------

# arq's ``cron()`` cannot pass arguments to the scheduled coroutine, and the
# supplier list lives in the database: each tick reads the table when it
# fires and enqueues one dedicated job per due supplier.


def _catalog_sync_due(
    *, interval_hours: int, last_started_at: datetime | None, now: datetime
) -> bool:
    """A catalog sync is due when none ran within the supplier's interval."""
    if interval_hours <= 0:
        return False
    if last_started_at is None:
        return True
    return _as_utc(last_started_at) <= now - timedelta(hours=interval_hours)


async def _due_suppliers(
    session: AsyncSession, *, catalog: bool
) -> list[tuple[str, list[str]]]:
    """Codes (and default categories) of the API suppliers to enqueue."""
    due: list[tuple[str, list[str]]] = []
    now = _now()
    for supplier, adapter in await api_suppliers(session):
        if not adapter.is_sync_enabled() or not adapter.is_configured():
            continue
        if catalog:
            recent = await supplier_sync_log_crud.get_recent_syncs(
                session,
                supplier_name=supplier.code,
                sync_type=SyncType.PRODUCT_CATALOG,
                hours=max(int(adapter.sync_interval_hours()), 1) * 2,
                limit=1,
            )
            last = recent[0].started_at if recent else None
            if not _catalog_sync_due(
                interval_hours=int(adapter.sync_interval_hours()),
                last_started_at=last,
                now=now,
            ):
                continue
        due.append((supplier.code, list(adapter.default_categories)))
    return due


async def scheduled_supplier_catalog_sync_task(
    _ctx: dict[str, Any], *_args: Any, **_kwargs: Any
) -> dict[str, Any]:
    """Hourly tick: enqueue a catalog sync for every supplier whose interval elapsed."""
    enqueued: list[str] = []
    async with AsyncSession(engine) as session:
        due = await _due_suppliers(session, catalog=True)
    for code, categories in due:
        try:
            await trigger_manual_sync(code, categories=categories or None)
            enqueued.append(code)
        except Exception as exc:  # noqa: BLE001
            logger.error("Cannot enqueue catalog sync for %s: %s", code, exc)
    return {"status": "ok", "enqueued": enqueued, "timestamp": _now().isoformat()}


async def scheduled_supplier_inventory_sync_task(
    _ctx: dict[str, Any],
) -> dict[str, Any]:
    """Two-hourly tick: enqueue a price & availability refresh per API supplier."""
    enqueued: list[str] = []
    async with AsyncSession(engine) as session:
        due = await _due_suppliers(session, catalog=False)
    for code, _categories in due:
        try:
            await trigger_inventory_refresh(code)
            enqueued.append(code)
        except Exception as exc:  # noqa: BLE001
            logger.error("Cannot enqueue inventory sync for %s: %s", code, exc)
    return {"status": "ok", "enqueued": enqueued, "timestamp": _now().isoformat()}


async def scheduled_supplier_health_check_task(
    _ctx: dict[str, Any], *_args: Any, **_kwargs: Any
) -> dict[str, Any]:
    """Daily tick: probe every API supplier."""
    results: dict[str, str] = {}
    async with AsyncSession(engine) as session:
        pairs = await api_suppliers(session)
    for supplier, adapter in pairs:
        try:
            health = await adapter.health_check()
            results[supplier.code] = "healthy" if health.healthy else "unhealthy"
        except Exception as exc:  # noqa: BLE001
            results[supplier.code] = f"error: {exc}"
    return {"status": "ok", "results": results, "timestamp": _now().isoformat()}


def get_supplier_sync_cron_jobs() -> list[Any]:
    """Build the three scheduler ticks (the supplier list is read at run time)."""
    return [
        cron(
            scheduled_supplier_catalog_sync_task,  # type: ignore[arg-type]
            hour=set(range(0, 24)),
            minute=0,
            second=0,
            name="supplier_catalog_sync_tick",
        ),
        cron(
            scheduled_supplier_inventory_sync_task,  # type: ignore[arg-type]
            hour=set(range(0, 24, INVENTORY_SYNC_EVERY_HOURS)),
            minute=30,
            second=0,
            name="supplier_inventory_sync_tick",
        ),
        cron(
            scheduled_supplier_health_check_task,  # type: ignore[arg-type]
            hour=6,
            minute=0,
            second=0,
            name="supplier_api_health_check_tick",
        ),
    ]


# -- manual triggers ------------------------------------------------------


async def trigger_manual_sync(
    supplier_name: str, categories: list[str] | None = None
) -> str:
    """Queue a catalog sync for ``supplier_name``; returns the ARQ job ID."""
    return await enqueue_with_dedup(
        "sync_supplier_products_task",
        dedup_namespace=f"manual_sync_dedup:{supplier_name}",
        job_prefix=f"manual_sync_{supplier_name}",
        payload_key=categories,
        job_kwargs={"supplier_name": supplier_name, "categories": categories},
    )


async def trigger_inventory_refresh(
    supplier_name: str, skus: list[str] | None = None
) -> str:
    """Queue an inventory refresh for ``supplier_name``; returns the ARQ job ID."""
    return await enqueue_with_dedup(
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
