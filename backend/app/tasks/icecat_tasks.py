"""
ARQ tasks for Icecat product enrichment.
Handles background jobs for enriching products with Icecat data (images, specifications, etc.)
"""

import datetime
import logging
from typing import Any, cast
from uuid import UUID

from arq import cron
from sqlalchemy import update as sa_update
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.core.db import engine
from app.features.integrations.models.icecat_sync import IcecatProductData
from app.features.integrations.services.supplier_data_normalization import (
    evaluate_product_filters,
)
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product, ProductUpdate
from app.features.product.services.overrides import strip_locked
from app.features.system.modules import module_enabled
from app.services.icecat_service import icecat_service

logger = logging.getLogger(__name__)


def update_product_with_icecat_data(
    icecat_product_data: IcecatProductData,
) -> ProductUpdate:
    """
    Create a ProductUpdate object from IcecatProductData

    Args:
        icecat_product_data: Icecat product data
    Returns:
        ProductUpdate object with fields to update
    """
    update_data = ProductUpdate()

    if icecat_product_data.description:
        update_data.description = icecat_product_data.description

    if icecat_product_data.long_description:
        update_data.long_description = icecat_product_data.long_description

    if icecat_product_data.specifications:
        update_data.technical_specifications = icecat_product_data.specifications

    if icecat_product_data.features:
        update_data.features = icecat_product_data.features

    if icecat_product_data.images:
        update_data.icecat_images = icecat_product_data.images

    if icecat_product_data.release_date:
        update_data.release_date = icecat_product_data.release_date

    if icecat_product_data.end_of_life_date:
        update_data.end_of_life_date = icecat_product_data.end_of_life_date

    if icecat_product_data.image_url:
        update_data.image_url = icecat_product_data.image_url

    if icecat_product_data.icecat_id:
        update_data.enrichment_supplier_id = icecat_product_data.icecat_id

    if icecat_product_data.weight_kg is not None:
        update_data.weight = icecat_product_data.weight_kg

    if icecat_product_data.dimensions_length_cm is not None:
        update_data.dimensions_length = icecat_product_data.dimensions_length_cm

    if icecat_product_data.dimensions_width_cm is not None:
        update_data.dimensions_width = icecat_product_data.dimensions_width_cm

    if icecat_product_data.dimensions_height_cm is not None:
        update_data.dimensions_height = icecat_product_data.dimensions_height_cm

    update_data.is_enriched = True
    update_data.last_enrichment_sync = datetime.datetime.now(tz=datetime.UTC)

    return update_data


def enrichment_payload(
    product: Product, icecat_product_data: IcecatProductData
) -> dict[str, Any]:
    """Champs à appliquer sur ``product`` : l'enrichissement moins les verrous.

    Un admin qui a corrigé la description ou l'image (A14) ne doit pas la voir
    revenir à la valeur Icecat au prochain passage — même règle que la sync
    fournisseur, voir ``product/services/overrides.py``. Les marqueurs
    ``is_enriched`` / ``last_enrichment_sync`` ne sont jamais verrouillés.
    """
    update_data = update_product_with_icecat_data(icecat_product_data)
    return strip_locked(
        update_data.model_dump(exclude_unset=True), product.overridden_fields
    )


async def enrich_product_with_icecat_task(
    _ctx: dict[str, Any], product_id: str
) -> dict[str, Any]:
    """
    Background task to enrich a single product with Icecat data

    Args:
        ctx: ARQ context
        product_id: Product ID to enrich

    Returns:
        Dictionary with enrichment result
    """

    logger.info(f"Starting Icecat enrichment for product ID: {product_id}")

    try:
        product_uuid = UUID(product_id)
    except ValueError:
        logger.error("Invalid product ID: %s", product_id)
        return {"status": "error", "message": "Invalid product ID"}

    async with AsyncSession(engine) as session:
        if not await module_enabled(session, "icecat"):
            logger.info("Icecat enrichment is switched off: %s skipped", product_id)
            return {"status": "disabled", "message": "Icecat enrichment is off"}
        try:
            # Get product from database
            product = await crud_product.read(session, id=product_uuid)

            if not product:
                logger.error(f"Product not found: {product_id}")
                return {"status": "error", "message": "Product not found"}

            if not getattr(product, "is_admin_active", True):
                logger.info(
                    "Skipping Icecat enrichment for product %s: is_admin_active=False",
                    product_id,
                )
                return {
                    "status": "skipped",
                    "message": "Product is admin inactive",
                }

            # Skip if product doesn't have vendor part number
            if not product.vendor_part_number or not product.manufacturer:
                logger.warning(
                    f"Product {product_id} missing vendor part number or manufacturer"
                )
                return {
                    "status": "skipped",
                    "message": "Missing required data for Icecat lookup",
                }

            # Get Icecat enrichment data
            enrichment_data: (
                IcecatProductData | None
            ) = await icecat_service.enrich_product_with_icecat(
                vendor_part_number=product.vendor_part_number,
                manufacturer=product.manufacturer,
                ean=product.ean if hasattr(product, "ean") else None,
                upc=product.upc if hasattr(product, "upc") else None,
            )

            if not enrichment_data:
                logger.warning(f"No Icecat data found for product {product_id}")
                return {"status": "not_found", "message": "No Icecat data available"}

            # Prepare update data (admin-locked fields left untouched)
            update_data = enrichment_payload(product, enrichment_data)

            # Level 2 filter: check UNSPSC codes returned by Icecat
            unspsc_codes = [
                spec["value"]
                for spec in (enrichment_data.specifications or [])
                if spec.get("name") == "Code UNSPSC" and spec.get("value")
            ]
            filter_action = evaluate_product_filters(
                supplier_name=product.supplier_name or "",
                unspsc_codes=unspsc_codes,
                rules=settings.SUPPLIER_PRODUCT_FILTER_RULES,
            )
            if filter_action in ("skip", "deactivate"):
                update_data["is_active"] = False
                logger.info(
                    "Product %s deactivated post-enrichment — UNSPSC codes %s matched a filter rule",
                    product_id,
                    unspsc_codes,
                )

            # Update product in database
            if update_data:
                updated_product = await crud_product.update(
                    session, id=product_uuid, data=update_data, record=product
                )

                # Project normalized specs into product_spec table
                from app.features.product.services.spec_projection import (
                    upsert_product_specs,
                )

                specs_count = await upsert_product_specs(session, updated_product)

                await session.commit()

                logger.info(
                    f"Successfully enriched product {product_id} with Icecat data ({specs_count} specs projected)"
                )
                return {
                    "status": "success",
                    "product_id": product_id,
                    "enriched_fields": list(update_data.keys()),
                    "specs_projected": specs_count,
                }
            else:
                return {
                    "status": "no_updates",
                    "message": "No fields to update",
                }

        except Exception as e:
            logger.error(f"Error enriching product {product_id} with Icecat: {e}")
            await session.rollback()
            return {"status": "error", "message": str(e)}


async def _stamp_enrichment_attempt(session: AsyncSession, product_id: UUID) -> None:
    """Record an enrichment attempt timestamp without marking the product enriched.

    Used for ``not_found`` / error outcomes so the product drops out of the
    batch candidate set for ``ICECAT_ENRICHMENT_RETRY_COOLDOWN_DAYS`` instead of
    being re-fetched (and re-queried against Icecat) on every run. Uses a direct
    UPDATE so it works even after a rolled-back session.
    """
    from app.features.product.models.product import Product

    now = datetime.datetime.now(tz=datetime.UTC)
    await session.execute(
        sa_update(Product)
        .where(col(Product.id) == product_id)
        .values(last_enrichment_sync=now)
    )
    await session.commit()


async def batch_enrich_products_task(
    _ctx: dict[str, Any], limit: int = 50
) -> dict[str, Any]:
    """
    Background task to batch enrich products with Icecat data

    Args:
        ctx: ARQ context
        limit: Maximum number of products to process

    Returns:
        Dictionary with batch enrichment statistics
    """
    from app.features.product.models.product import Product

    logger.info(f"Starting batch Icecat enrichment for up to {limit} products")

    stats = {
        "total_processed": 0,
        "enriched": 0,
        "skipped": 0,
        "not_found": 0,
        "errors": 0,
    }

    async with AsyncSession(engine) as session:
        if not await module_enabled(session, "icecat"):
            logger.info("Icecat enrichment is switched off: batch skipped")
            return {**stats, "status": "disabled"}
        try:
            # Query products that need enrichment:
            # - Have supplier managed flag
            # - Not yet enriched with Icecat
            # - Have vendor part number and manufacturer
            # - Not attempted within the retry cooldown (so un-matchable SKUs
            #   don't get re-queried against Icecat every run). Never-attempted
            #   products (last_enrichment_sync IS NULL) are prioritised first.
            cooldown_days = await runtime_settings.get(
                "icecat_enrichment_retry_cooldown_days", session
            )
            cooldown_cutoff = datetime.datetime.now(
                tz=datetime.UTC
            ) - datetime.timedelta(days=int(cooldown_days))
            query = (
                select(Product)
                .where(col(Product.is_supplier_managed).is_(True))
                .where(col(Product.is_admin_active).is_(True))
                .where(
                    col(Product.is_enriched).is_(False)
                    | col(Product.is_enriched).is_(None)
                )
                .where(col(Product.vendor_part_number).is_not(None))
                .where(col(Product.manufacturer).is_not(None))
                .where(
                    col(Product.last_enrichment_sync).is_(None)
                    | (col(Product.last_enrichment_sync) < cooldown_cutoff)
                )
                .order_by(col(Product.last_enrichment_sync).asc().nullsfirst())
                .limit(limit)
            )

            result = await session.exec(query)
            products = result.all()

            logger.info(f"Found {len(products)} products to enrich")

            for product in products:
                stats["total_processed"] += 1
                await session.refresh(product)
                product_id = product.id

                if not getattr(product, "is_admin_active", True):
                    stats["skipped"] += 1
                    logger.info(
                        "Skipping Icecat enrichment for product %s: is_admin_active=False",
                        product_id,
                    )
                    continue

                try:
                    # Get Icecat enrichment data
                    enrichment_data = await icecat_service.enrich_product_with_icecat(
                        vendor_part_number=product.vendor_part_number,
                        manufacturer=product.manufacturer,
                        ean=product.ean if hasattr(product, "ean") else None,
                        # The single-product task has always passed this; the
                        # batch did not, so the same product matched when
                        # enriched by hand and missed in the nightly run.
                        upc=product.upc if hasattr(product, "upc") else None,
                    )

                    if not enrichment_data:
                        stats["not_found"] += 1
                        # Stamp the attempt so this un-matchable SKU isn't
                        # re-queried against Icecat until the cooldown elapses.
                        await _stamp_enrichment_attempt(session, product_id)
                        continue

                    # Prepare update data (admin-locked fields left untouched)
                    update_data = enrichment_payload(product, enrichment_data)

                    # Level 2 filter: check UNSPSC codes returned by Icecat
                    unspsc_codes = [
                        spec["value"]
                        for spec in (enrichment_data.specifications or [])
                        if spec.get("name") == "Code UNSPSC" and spec.get("value")
                    ]
                    filter_action = evaluate_product_filters(
                        supplier_name=product.supplier_name or "",
                        unspsc_codes=unspsc_codes,
                        rules=settings.SUPPLIER_PRODUCT_FILTER_RULES,
                    )
                    if filter_action in ("skip", "deactivate"):
                        update_data["is_active"] = False
                        logger.info(
                            "Product %s deactivated post-enrichment — UNSPSC %s matched a filter rule",
                            product.id,
                            unspsc_codes,
                        )

                    updated_product = await crud_product.update(
                        session, id=product_id, data=update_data, record=product
                    )

                    # Project normalized specs into product_spec table so spec
                    # facets (CPU/RAM/…) work for batch-enriched products too.
                    from app.features.product.services.spec_projection import (
                        upsert_product_specs,
                    )

                    await upsert_product_specs(session, updated_product)

                    stats["enriched"] += 1

                    # Commit after each product to avoid losing progress
                    await session.commit()

                except Exception as e:
                    logger.error(
                        f"Error enriching product {product.id} with Icecat: {e}"
                    )
                    stats["errors"] += 1
                    await session.rollback()
                    # Back off this product for the cooldown window so a
                    # persistent error doesn't get retried every run.
                    try:
                        await _stamp_enrichment_attempt(session, product_id)
                    except Exception as stamp_exc:  # noqa: BLE001
                        logger.warning(
                            "Failed to stamp enrichment attempt for %s: %s",
                            product_id,
                            stamp_exc,
                        )

            logger.info(f"Batch Icecat enrichment completed. Stats: {stats}")

            # Re-enqueue while a full batch was found: every fetched product is
            # now either enriched or stamped (cooldown), so the eligible set
            # shrinks by `limit` each run and the loop is bounded. This drains
            # the backlog in minutes instead of one batch per cron tick.
            if len(products) >= limit:
                try:
                    next_job = await trigger_batch_enrichment(limit=limit)
                    stats["requeued"] = 1
                    logger.info(
                        "Re-enqueued batch Icecat enrichment (job %s) — more "
                        "products remain",
                        next_job,
                    )
                except Exception as enqueue_exc:  # noqa: BLE001
                    logger.warning(
                        "Failed to re-enqueue batch Icecat enrichment: %s",
                        enqueue_exc,
                    )

            return stats

        except Exception as e:
            logger.error(f"Error in batch Icecat enrichment: {e}")
            return {"status": "error", "message": str(e), "stats": stats}


async def trigger_product_enrichment(product_id: str) -> str:
    """
    Trigger Icecat enrichment for a single product

    Args:
        product_id: Product ID to enrich

    Returns:
        Job ID
    """
    from app.core.arq_pool import get_arq_pool

    arq_pool = await get_arq_pool()  # type: ignore[no-untyped-call]

    job = await arq_pool.enqueue_job(
        "enrich_product_with_icecat_task", product_id=product_id
    )
    return cast(str, job.job_id)


async def reproject_product_specs_task(
    _ctx: dict[str, Any], category_id: str | None = None
) -> dict[str, Any]:
    """Re-project spec_definitions.yaml onto all enriched products.

    Run this after any alias modification in spec_definitions.yaml to rebuild
    the product_spec table without re-fetching Icecat data.

    Args:
        category_id: Optional UUID string to limit re-projection to one category.
    """
    from app.features.product.models.product import Product
    from app.features.product.services.spec_projection import upsert_product_specs

    logger.info("Starting spec re-projection task (category_id=%s)", category_id)
    stats = {"total": 0, "projected": 0, "errors": 0}

    async with AsyncSession(engine) as session:
        try:
            query = (
                select(Product)
                .where(col(Product.is_enriched).is_(True))
                .where(col(Product.is_active).is_(True))
            )
            if category_id:
                import uuid as _uuid

                query = query.where(Product.category_id == _uuid.UUID(category_id))

            result = await session.exec(query)
            products = list(result.all())
            stats["total"] = len(products)

            for product in products:
                try:
                    count = await upsert_product_specs(session, product)
                    if count:
                        stats["projected"] += 1
                except Exception as exc:  # noqa: BLE001
                    logger.error(
                        "Error projecting specs for product %s: %s", product.id, exc
                    )
                    stats["errors"] += 1

            await session.commit()
            logger.info("Spec re-projection complete. Stats: %s", stats)
            return {"status": "success", **stats}

        except Exception as exc:  # noqa: BLE001
            logger.error("Error in spec re-projection task: %s", exc)
            return {"status": "error", "message": str(exc), **stats}


async def enqueue_reproject_product_specs(category_id: str | None = None) -> str:
    """Enqueue a spec re-projection job. Returns the ARQ job id."""
    from app.core.arq_pool import get_arq_pool

    arq_pool = await get_arq_pool()  # type: ignore[no-untyped-call]
    job = await arq_pool.enqueue_job(
        "reproject_product_specs_task", category_id=category_id
    )
    return cast(str, job.job_id)


async def trigger_batch_enrichment(limit: int = 50) -> str:
    """
    Trigger batch Icecat enrichment

    Args:
        limit: Maximum number of products to process

    Returns:
        Job ID
    """
    from app.core.arq_pool import get_arq_pool

    arq_pool = await get_arq_pool()  # type: ignore[no-untyped-call]

    job = await arq_pool.enqueue_job("batch_enrich_products_task", limit=limit)
    return cast(str, job.job_id)


# -- cron scheduling ----------------------------------------------------------
# arq's ``cron()`` cannot pass arguments to the scheduled coroutine, so we wrap
# the batch task to inject the configured limit.


def _due(now: datetime.datetime, interval_hours: int) -> bool:
    """Whether the hourly tick at ``now`` is one of every ``interval_hours``."""
    if interval_hours <= 0:
        return False
    hours_since_epoch = int(now.timestamp()) // 3600
    return hours_since_epoch % interval_hours == 0


async def scheduled_batch_enrich_task(_ctx: dict[str, Any]) -> dict[str, Any]:
    """Hourly tick of the recurring batch enrichment (R5 / C5).

    Always scheduled: the interval and the batch size are read from the
    runtime settings at each tick, so a change in the back-office applies
    without restarting the worker (0 = never).
    """
    from app.core import runtime_settings

    if not settings.ICECAT_ENABLED:
        return {"status": "disabled"}
    values = await runtime_settings.get_many(
        ["icecat_enrichment_interval_hours", "icecat_batch_enrich_limit"]
    )
    now = datetime.datetime.now(tz=datetime.UTC)
    if not _due(now, int(values["icecat_enrichment_interval_hours"])):
        return {"status": "not_due"}
    return await batch_enrich_products_task(
        _ctx, limit=int(values["icecat_batch_enrich_limit"])
    )


def get_enrichment_cron_jobs() -> list[Any]:
    """The hourly tick of the Icecat batch enrichment (always scheduled; the
    tick decides from the runtime settings whether it is due)."""
    return [
        cron(
            scheduled_batch_enrich_task,  # type: ignore[arg-type]
            minute=15,
            second=0,
            name="icecat_batch_enrichment",
        )
    ]
