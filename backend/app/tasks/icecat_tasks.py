"""
ARQ tasks for Icecat product enrichment.
Handles background jobs for enriching products with Icecat data (images, specifications, etc.)
"""

import datetime
import logging
from typing import Any, cast
from uuid import UUID

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.features.integrations.models.icecat_sync import IcecatProductData
from app.features.product.crud.product import crud_product
from app.features.product.models.product import ProductUpdate
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

    update_data.is_enriched = True
    update_data.last_enrichment_sync = datetime.datetime.now(tz=datetime.timezone.utc)

    return update_data


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
        try:
            # Get product from database
            product = await crud_product.read(session, id=product_uuid)

            if not product:
                logger.error(f"Product not found: {product_id}")
                return {"status": "error", "message": "Product not found"}

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

            # Prepare update data
            update_data = update_product_with_icecat_data(enrichment_data)

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
                    "enriched_fields": list(
                        update_data.dict(exclude_unset=True).keys()
                    ),
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
        try:
            # Query products that need enrichment:
            # - Have supplier managed flag
            # - Not yet enriched with Icecat
            # - Have vendor part number and manufacturer
            query = (
                select(Product)
                .where(col(Product.is_supplier_managed).is_(True))
                .where(
                    col(Product.is_enriched).is_(False)
                    | col(Product.is_enriched).is_(None)
                )
                .where(col(Product.vendor_part_number).is_not(None))
                .where(col(Product.manufacturer).is_not(None))
                .limit(limit)
            )

            result = await session.exec(query)
            products = result.all()

            logger.info(f"Found {len(products)} products to enrich")

            for product in products:
                stats["total_processed"] += 1
                await session.refresh(product)
                product_id = product.id

                try:
                    # Get Icecat enrichment data
                    enrichment_data = await icecat_service.enrich_product_with_icecat(
                        vendor_part_number=product.vendor_part_number,
                        manufacturer=product.manufacturer,
                        ean=product.ean if hasattr(product, "ean") else None,
                    )

                    if not enrichment_data:
                        stats["not_found"] += 1
                        continue

                    # Prepare update data
                    update_data = update_product_with_icecat_data(enrichment_data)

                    await crud_product.update(
                        session, id=product_id, data=update_data, record=product
                    )

                    stats["enriched"] += 1

                    # Commit after each product to avoid losing progress
                    await session.commit()

                except Exception as e:
                    logger.error(
                        f"Error enriching product {product.id} with Icecat: {e}"
                    )
                    stats["errors"] += 1
                    await session.rollback()

            logger.info(f"Batch Icecat enrichment completed. Stats: {stats}")
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
