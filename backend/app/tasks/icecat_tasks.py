"""
ARQ tasks for Icecat product enrichment.
Handles background jobs for enriching products with Icecat data (images, specifications, etc.)
"""

import logging
from typing import Any

from sqlmodel import select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.db import engine
from app.services.icecat_service import icecat_service

logger = logging.getLogger(__name__)


async def enrich_product_with_icecat_task(
    ctx: dict[str, Any], product_id: str
) -> dict[str, Any]:
    """
    Background task to enrich a single product with Icecat data

    Args:
        ctx: ARQ context
        product_id: Product ID to enrich

    Returns:
        Dictionary with enrichment result
    """
    from app.features.product.crud.product import crud_product

    logger.info(f"Starting Icecat enrichment for product ID: {product_id}")

    async with AsyncSession(engine) as session:
        try:
            # Get product from database
            product = await crud_product.get(session=session, id=product_id)

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
            enrichment_data = await icecat_service.enrich_product_with_icecat(
                vendor_part_number=product.vendor_part_number,
                manufacturer=product.manufacturer,
                ean=product.ean if hasattr(product, "ean") else None,
            )

            if not enrichment_data:
                logger.info(f"No Icecat data found for product {product_id}")
                return {"status": "not_found", "message": "No Icecat data available"}

            # Update product with enrichment data
            update_data = {}

            # Update long description if available and product doesn't have one
            if enrichment_data.get("long_description") and not product.long_description:
                update_data["long_description"] = enrichment_data["long_description"]

            # Update specifications (store as JSON)
            if enrichment_data.get("specifications"):
                update_data["technical_specifications"] = enrichment_data[
                    "specifications"
                ]

            # Update features
            if enrichment_data.get("features"):
                update_data["features"] = enrichment_data["features"]

            # Update images URLs (store as list)
            if enrichment_data.get("images"):
                update_data["icecat_images"] = enrichment_data["images"]
                # Set main image if not set
                if enrichment_data.get("main_image_url") and not product.image_url:
                    update_data["image_url"] = enrichment_data["main_image_url"]

            # Mark as enriched with Icecat
            update_data["icecat_enriched"] = True
            update_data["icecat_last_update"] = "now"

            # Update product in database
            if update_data:
                await crud_product.update(
                    session=session, record=product, data=update_data
                )
                await session.commit()

                logger.info(
                    f"Successfully enriched product {product_id} with Icecat data"
                )
                return {
                    "status": "success",
                    "product_id": product_id,
                    "enriched_fields": list(update_data.keys()),
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
    ctx: dict[str, Any], limit: int = 50
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
                .where(Product.is_supplier_managed == True)
                .where(
                    (Product.icecat_enriched == False)
                    | (Product.icecat_enriched == None)
                )
                .where(Product.vendor_part_number != None)
                .where(Product.manufacturer != None)
                .limit(limit)
            )

            result = await session.execute(query)
            products = result.scalars().all()

            logger.info(f"Found {len(products)} products to enrich")

            for product in products:
                stats["total_processed"] += 1

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

                    # Update product with enrichment data
                    update_data = {}

                    if (
                        enrichment_data.get("long_description")
                        and not product.long_description
                    ):
                        update_data["long_description"] = enrichment_data[
                            "long_description"
                        ]

                    if enrichment_data.get("specifications"):
                        update_data["technical_specifications"] = enrichment_data[
                            "specifications"
                        ]

                    if enrichment_data.get("features"):
                        update_data["features"] = enrichment_data["features"]

                    if enrichment_data.get("images"):
                        update_data["icecat_images"] = enrichment_data["images"]
                        if (
                            enrichment_data.get("main_image_url")
                            and not product.image_url
                        ):
                            update_data["image_url"] = enrichment_data["main_image_url"]

                    update_data["icecat_enriched"] = True

                    # Update product
                    from app.features.product.crud.product import crud_product

                    await crud_product.update(
                        session=session, record=product, data=update_data
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

    arq_pool = await get_arq_pool()

    job = await arq_pool.enqueue_job(
        "enrich_product_with_icecat_task", product_id=product_id
    )
    return job.job_id


async def trigger_batch_enrichment(limit: int = 50) -> str:
    """
    Trigger batch Icecat enrichment

    Args:
        limit: Maximum number of products to process

    Returns:
        Job ID
    """
    from app.core.tasks import arq_pool

    job = await arq_pool.enqueue_job("batch_enrich_products_task", limit=limit)
    return job.job_id
