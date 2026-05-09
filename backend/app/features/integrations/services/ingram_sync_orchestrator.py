"""
Integration orchestrator for Ingram product synchronization.

This module contains application-level synchronization workflows:
- mapping Ingram API payloads to local product schemas
- upsert strategy by supplier identity
- transaction handling and commit strategy
"""

import asyncio
import logging
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.product.crud.product import crud_product
from app.features.product.models.product import ProductCreate, ProductUpdate
from app.services.ingram_micro_service import (
    IngramMicroService,
    IngramProductData,
    ingram_service,
)

logger = logging.getLogger(__name__)


class IngramSyncOrchestrator:
    """Application-level orchestrator for Ingram synchronization workflows."""

    def __init__(self, ingram_api: IngramMicroService | None = None) -> None:
        self.ingram_api = ingram_api or ingram_service

    def _convert_ingram_to_product_data(
        self, ingram_product: IngramProductData
    ) -> dict[str, Any]:
        """Convert Ingram product payload into local product schema fields."""
        return {
            "name": ingram_product.product_name,
            "description": ingram_product.description
            or f"{ingram_product.manufacturer} {ingram_product.product_name}",
            "has_variants": False,
            "supplier_sku": ingram_product.sku,
            "vendor_part_number": ingram_product.vendor_part_number,
            "manufacturer": ingram_product.manufacturer,
            "supplier_name": "Ingram Micro",
            "supplier_category": ingram_product.category,
            "supplier_subcategory": ingram_product.subcategory,
            "weight": ingram_product.weight,
            "supplier_image_url": ingram_product.image_url,
            "supplier_spec_url": ingram_product.specification_url,
            "is_supplier_managed": True,
            "is_active": True,
            "upc": ingram_product.upc_code,
        }

    async def upsert_product(
        self, session: AsyncSession, ingram_product: IngramProductData
    ) -> dict[str, str]:
        """Insert or update a local product from one Ingram payload."""
        existing_product = await crud_product.get_by_supplier_sku(
            session=session,
            supplier_sku=ingram_product.sku,
            supplier_name="Ingram Micro",
        )

        product_data_dict = self._convert_ingram_to_product_data(ingram_product)

        if existing_product:
            product_update = ProductUpdate(**product_data_dict)
            updated_product = await crud_product.update(
                session=session,
                id=existing_product.id,
                data=product_update,
                user=None,
            )
            return {"action": "updated", "product_id": str(updated_product.id)}

        product_create = ProductCreate(**product_data_dict)
        new_product = await crud_product.create(
            session=session,
            data=product_create,
            user=None,
        )
        return {"action": "created", "product_id": str(new_product.id)}

    async def sync_products_to_database(
        self, session: AsyncSession, categories: list[str]
    ) -> dict[str, int]:
        """
        Synchronize products from Ingram Micro to the local database.

        This orchestrator owns application-level behavior (upsert + commit strategy).
        """
        stats = {
            "total_fetched": 0,
            "new_products": 0,
            "updated_products": 0,
            "skipped_products": 0,
            "errors": 0,
        }

        logger.debug("Starting orchestrated product sync for categories: %s", categories)

        for category in categories:
            try:
                page = 1
                page_size = 100

                while True:
                    products = await self.ingram_api.get_product_catalog(
                        category=category,
                        page_number=page,
                        page_size=page_size,
                    )

                    if not products:
                        break

                    stats["total_fetched"] += len(products)

                    for product in products:
                        if not product.sku or not product.product_name:
                            stats["skipped_products"] += 1
                            continue

                        try:
                            result = await self.upsert_product(session, product)

                            if result["action"] == "created":
                                stats["new_products"] += 1
                            elif result["action"] == "updated":
                                stats["updated_products"] += 1

                            await session.commit()

                        except Exception as e:
                            logger.error("Error syncing product %s: %s", product.sku, e)
                            stats["errors"] += 1
                            await session.rollback()
                            continue

                    page += 1
                    await asyncio.sleep(0.5)

            except Exception as e:
                logger.error("Error syncing category %s: %s", category, e)
                stats["errors"] += 1

        logger.debug("Orchestrated product sync completed. Stats: %s", stats)
        return stats


ingram_sync_orchestrator = IngramSyncOrchestrator()
