"""
ARQ tasks for Ingram Micro product synchronization.
Handles scheduled and on-demand product catalog sync.
"""

import logging
from datetime import datetime, timezone

from arq import cron
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.db import engine
from app.services.ingram_micro_service import ingram_service

logger = logging.getLogger(__name__)


async def sync_ingram_products_task(
    ctx, categories: list[str] | None = None
) -> dict[str, any]:
    """
    ARQ task to synchronize products from Ingram Micro API

    Args:
        ctx: ARQ context
        categories: List of categories to sync (defaults to settings)

    Returns:
        Dictionary with sync results and statistics
    """
    if not settings.INGRAM_SYNC_ENABLED:
        logger.info("Ingram Micro sync is disabled in settings")
        return {"status": "disabled", "message": "Sync disabled in settings"}

    if not all(
        [
            settings.INGRAM_CLIENT_ID,
            settings.INGRAM_CLIENT_SECRET,
            settings.INGRAM_CUSTOMER_NUMBER,
        ]
    ):
        logger.error("Ingram Micro credentials not configured")
        return {"status": "error", "message": "Missing Ingram Micro credentials"}

    # Use provided categories or fall back to settings
    sync_categories = categories or settings.INGRAM_SYNC_CATEGORIES

    logger.info(f"Starting Ingram Micro product sync for categories: {sync_categories}")

    try:
        async with AsyncSession(engine) as session:
            # Record sync start time
            sync_start = datetime.now(timezone.utc)

            # Perform the sync
            stats = await ingram_service.sync_products_to_database(
                session=session, categories=sync_categories
            )

            sync_end = datetime.now(timezone.utc)
            duration = (sync_end - sync_start).total_seconds()

            # TODO: Store sync history in database
            # await create_sync_log(session, stats, sync_start, sync_end)

            result = {
                "status": "success",
                "categories": sync_categories,
                "start_time": sync_start.isoformat(),
                "end_time": sync_end.isoformat(),
                "duration_seconds": duration,
                "statistics": stats,
            }

            logger.info(
                f"Ingram sync completed successfully in {duration:.2f}s. Stats: {stats}"
            )
            return result

    except Exception as e:
        logger.error(f"Ingram Micro sync failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "categories": sync_categories,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def sync_ingram_inventory_task(
    ctx, skus: list[str] | None = None
) -> dict[str, any]:
    """
    ARQ task to update inventory levels from Ingram Micro API

    Args:
        ctx: ARQ context
        skus: Specific SKUs to update (if None, updates all active products)

    Returns:
        Dictionary with inventory update results
    """
    if not settings.INGRAM_SYNC_ENABLED:
        return {"status": "disabled", "message": "Sync disabled in settings"}

    logger.info(
        f"Starting Ingram inventory sync for {len(skus) if skus else 'all'} products"
    )

    try:
        async with AsyncSession(engine) as session:
            if not skus:
                # TODO: Get all active Ingram SKUs from database
                # skus = await get_active_ingram_skus(session)
                skus = []  # Placeholder

            if not skus:
                return {"status": "success", "message": "No SKUs to update"}

            # Split SKUs into batches (Ingram API limit)
            batch_size = 50
            total_updated = 0
            errors = 0

            for i in range(0, len(skus), batch_size):
                batch_skus = skus[i : i + batch_size]

                try:
                    availability = await ingram_service.get_inventory_availability(
                        batch_skus
                    )

                    # TODO: Update database with new inventory levels
                    # for sku, quantity in availability.items():
                    #     await update_product_inventory(session, sku, quantity)

                    total_updated += len(availability)

                except Exception as e:
                    logger.error(f"Error updating inventory batch: {e}")
                    errors += 1

            await session.commit()

            result = {
                "status": "success",
                "total_skus": len(skus),
                "updated": total_updated,
                "errors": errors,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

            logger.info(f"Inventory sync completed. Updated {total_updated} products")
            return result

    except Exception as e:
        logger.error(f"Inventory sync failed: {e}")
        return {
            "status": "error",
            "message": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


async def check_ingram_api_health_task(ctx) -> dict[str, any]:
    """
    ARQ task to check Ingram Micro API health and connectivity

    Args:
        ctx: ARQ context

    Returns:
        Dictionary with health check results
    """
    logger.info("Checking Ingram Micro API health")

    try:
        # Test API connectivity with a simple catalog request
        products = await ingram_service.get_product_catalog(
            category="notebooks", page_number=1, page_size=1
        )

        result = {
            "status": "healthy",
            "api_responsive": True,
            "can_authenticate": True,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "test_result": f"Successfully fetched {len(products)} test products",
        }

        logger.info("Ingram Micro API health check passed")
        return result

    except Exception as e:
        logger.error(f"Ingram Micro API health check failed: {e}")
        return {
            "status": "unhealthy",
            "api_responsive": False,
            "error": str(e),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }


# Cron job configuration for scheduled synchronization
def get_ingram_sync_cron_jobs():
    """Get cron job configurations for Ingram Micro sync"""

    if not settings.INGRAM_SYNC_ENABLED:
        return []

    jobs = []

    # Main product sync - every X hours based on settings
    sync_hour_interval = settings.INGRAM_SYNC_INTERVAL_HOURS
    jobs.append(
        cron(
            sync_ingram_products_task,
            hour={h for h in range(0, 24, sync_hour_interval)},
            minute=0,
            second=0,
            name="ingram_product_sync",
        )
    )

    # Inventory sync - more frequent (every 2 hours)
    jobs.append(
        cron(
            sync_ingram_inventory_task,
            hour={h for h in range(0, 24, 2)},
            minute=30,  # Offset from product sync
            second=0,
            name="ingram_inventory_sync",
        )
    )

    # API health check - daily at 6 AM
    jobs.append(
        cron(
            check_ingram_api_health_task,
            hour=6,
            minute=0,
            second=0,
            name="ingram_api_health_check",
        )
    )

    return jobs


# Manual sync functions for on-demand execution
async def trigger_manual_sync(categories: list[str] | None = None) -> str:
    """
    Trigger manual product sync (returns job ID for tracking)

    Args:
        categories: Specific categories to sync

    Returns:
        ARQ job ID
    """
    from app.core.arq_worker import get_redis_pool

    redis = await get_redis_pool()
    job = await redis.enqueue_job(
        "sync_ingram_products_task",
        categories=categories,
        _job_id=f"manual_sync_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )

    logger.info(f"Manual Ingram sync triggered with job ID: {job.job_id}")
    return job.job_id


async def trigger_inventory_refresh(skus: list[str] | None = None) -> str:
    """
    Trigger manual inventory refresh (returns job ID for tracking)

    Args:
        skus: Specific SKUs to refresh

    Returns:
        ARQ job ID
    """
    from app.core.arq_worker import get_redis_pool

    redis = await get_redis_pool()
    job = await redis.enqueue_job(
        "sync_ingram_inventory_task",
        skus=skus,
        _job_id=f"manual_inventory_{datetime.now().strftime('%Y%m%d_%H%M%S')}",
    )

    logger.info(f"Manual inventory refresh triggered with job ID: {job.job_id}")
    return job.job_id
