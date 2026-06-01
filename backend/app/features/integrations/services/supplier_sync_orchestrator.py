"""
Supplier-agnostic synchronization orchestrator.

Owns application-level sync behavior, independent of which distributor is being
synced:
- mapping normalized supplier payloads to the local product schema
- upsert strategy by supplier identity (persisted mapping first, then
  ``supplier_sku`` + ``supplier_name``)
- transaction / commit strategy

Each :class:`~app.services.suppliers.base.SupplierAdapter` provides the catalog
and price/availability data; this class never talks to a vendor API directly.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.integrations.crud.supplier_sync import supplier_product_mapping_crud
from app.features.integrations.models.supplier_sync import SupplierProductMapping
from app.features.integrations.services.supplier_data_normalization import (
    DEFAULT_CURRENCY,
    evaluate_product_filters,
    normalize_supplier_snapshot,
)
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product, ProductCreate, ProductUpdate
from app.services.suppliers import get_adapter
from app.services.suppliers.base import NormalizedProductData, SupplierAdapter
from app.tasks.icecat_tasks import trigger_batch_enrichment

logger = logging.getLogger(__name__)


class SupplierSyncOrchestrator:
    """Application-level orchestrator for one supplier's sync workflows."""

    def __init__(self, adapter: SupplierAdapter) -> None:
        """Initialize the supplier sync orchestrator instance."""
        self.adapter = adapter

    @property
    def supplier_name(self) -> str:
        """Execute supplier name."""
        return self.adapter.name

    @classmethod
    def for_supplier(cls, supplier_name: str) -> "SupplierSyncOrchestrator":
        """Build an orchestrator for the registered ``supplier_name``."""
        return cls(get_adapter(supplier_name))

    def _to_product_data(self, item: NormalizedProductData) -> dict[str, Any]:
        """Convert a normalized supplier payload into local product fields.

        Note: ``is_active`` is intentionally not set here. The catalog endpoint
        of most distributors (Ingram in particular) does not return price or
        availability, so the sync-threshold decision cannot be made at catalog
        time. ``is_active`` is computed by the inventory sync where real
        pricing data is available.
        """
        snapshot = normalize_supplier_snapshot(
            raw_price=item.price,
            raw_quantity=item.quantity,
            raw_currency=item.currency or DEFAULT_CURRENCY,
        )
        return {
            "name": item.name,
            "description": item.description
            or " ".join(filter(None, [item.manufacturer, item.name])),
            "base_price": snapshot.base_price,
            "has_variants": False,
            "supplier_sku": item.supplier_sku,
            "vendor_part_number": item.vendor_part_number,
            "manufacturer": item.manufacturer,
            "supplier_name": self.adapter.name,
            "supplier_category": item.category,
            "supplier_subcategory": item.subcategory,
            "weight": item.weight,
            "supplier_image_url": item.image_url,
            "supplier_spec_url": item.spec_url,
            "supplier_quantity": snapshot.supplier_quantity,
            "supplier_price": snapshot.supplier_price,
            "supplier_price_currency": snapshot.supplier_price_currency,
            "is_supplier_managed": True,
            "upc": item.upc,
            "ean": item.ean,
        }

    async def _resolve_existing_product(
        self, session: AsyncSession, item: NormalizedProductData
    ) -> tuple[Product | None, SupplierProductMapping | None]:
        """Resolve the target product: persisted mapping first, then supplier identity."""
        mapping = await supplier_product_mapping_crud.get_by_supplier_sku(
            session=session,
            supplier_name=self.adapter.name,
            supplier_sku=item.supplier_sku,
        )

        if mapping is not None:
            mapped_product = await session.get(Product, mapping.local_product_id)
            if (
                mapped_product is not None
                and mapped_product.is_supplier_managed
                and mapped_product.supplier_name == self.adapter.name
                and mapped_product.supplier_sku == item.supplier_sku
            ):
                return mapped_product, mapping

            logger.warning(
                "Supplier mapping mismatch for %s SKU %s (mapping_id=%s). "
                "Falling back to supplier identity.",
                self.adapter.name,
                item.supplier_sku,
                mapping.id,
            )

        supplier_product = await crud_product.get_by_supplier_sku(
            session=session,
            supplier_sku=item.supplier_sku,
            supplier_name=self.adapter.name,
            supplier_managed_only=True,
        )
        return supplier_product, mapping

    async def _upsert_mapping(
        self,
        session: AsyncSession,
        product: Product,
        item: NormalizedProductData,
    ) -> None:
        """Create or update the supplier→product mapping without committing.

        Avoids an internal commit so that product and mapping stay in the same
        transaction, committed once by the caller (sync_products_to_database).
        """
        sync_time = datetime.now(timezone.utc)
        mapping = await supplier_product_mapping_crud.get_by_supplier_sku(
            session=session,
            supplier_name=self.adapter.name,
            supplier_sku=item.supplier_sku,
        )
        if mapping is None:
            new_mapping = SupplierProductMapping(
                supplier_name=self.adapter.name,
                supplier_sku=item.supplier_sku,
                local_product_id=product.id,
                vendor_part_number=item.vendor_part_number,
                manufacturer=item.manufacturer,
                last_synced=sync_time,
                sync_enabled=True,
            )
            session.add(new_mapping)
            await session.flush()
        else:
            mapping.local_product_id = product.id
            mapping.vendor_part_number = item.vendor_part_number
            mapping.manufacturer = item.manufacturer
            mapping.last_synced = sync_time
            mapping.sync_enabled = True

    async def upsert_product(
        self, session: AsyncSession, item: NormalizedProductData
    ) -> dict[str, str]:
        """Insert or update a local product from one normalized supplier payload.

        Uses draft (no-commit) CRUD methods so that product + mapping land in one
        transaction committed by the caller.  Avoids mid-operation session expiry
        that would trigger a SQLAlchemy implicit lazy-load error in async mode.
        """
        from app.core.config import settings

        filter_action = evaluate_product_filters(
            supplier_name=self.adapter.name,
            supplier_subcategory=item.subcategory,
            supplier_category=item.category,
            name=item.name,
            rules=settings.SUPPLIER_PRODUCT_FILTER_RULES,
            subcategory_allowlist=settings.SUPPLIER_SYNC_SUBCATEGORY_ALLOWLIST,
        )

        if filter_action == "skip":
            logger.debug(
                "Skipping product %s (%s) — matched a 'skip' filter rule (subcategory=%s)",
                item.supplier_sku,
                self.adapter.name,
                item.subcategory,
            )
            return {"action": "filtered", "product_id": ""}

        existing_product, _existing_mapping = await self._resolve_existing_product(
            session=session, item=item
        )

        product_data_dict = self._to_product_data(item)

        if filter_action == "deactivate":
            logger.debug(
                "Deactivating product %s (%s) — matched a 'deactivate' filter rule (subcategory=%s)",
                item.supplier_sku,
                self.adapter.name,
                item.subcategory,
            )
            product_data_dict["is_active"] = False

        if existing_product:
            product = await crud_product.update_draft(
                session=session,
                id=existing_product.id,
                data=ProductUpdate(**product_data_dict),
                user=None,
                record=existing_product,
            )
            action = "updated"
        else:
            product = await crud_product.create_draft(
                session=session,
                data=ProductCreate(**product_data_dict),
                user=None,
            )
            action = "created"

        await self._upsert_mapping(session, product, item)

        return {
            "action": action,
            "product_id": str(product.id),
        }

    async def sync_products_to_database(
        self, session: AsyncSession, categories: list[str] | None = None
    ) -> dict[str, int]:
        """Synchronize the supplier catalog into the local database.

        Commits incrementally (one product per commit) so a failure mid-run
        does not roll back already-imported products.
        """
        sync_categories = list(categories or self.adapter.default_categories)
        stats = {
            "total_fetched": 0,
            "new_products": 0,
            "updated_products": 0,
            "skipped_products": 0,
            "filtered_products": 0,
            "errors": 0,
        }

        logger.debug(
            "Starting %s product sync for categories: %s",
            self.adapter.name,
            sync_categories,
        )

        for category in sync_categories:
            try:
                async for page in self.adapter.fetch_catalog(category=category):
                    stats["total_fetched"] += len(page)

                    for item in page:
                        if not item.supplier_sku or not item.name:
                            stats["skipped_products"] += 1
                            continue
                        try:
                            result = await self.upsert_product(session, item)
                            if result["action"] == "filtered":
                                stats["filtered_products"] += 1
                                continue
                            elif result["action"] == "created":
                                stats["new_products"] += 1
                            elif result["action"] == "updated":
                                stats["updated_products"] += 1
                            await session.commit()
                        except Exception as e:  # noqa: BLE001
                            logger.error(
                                "Error syncing product %s (%s): %s",
                                item.supplier_sku,
                                self.adapter.name,
                                e,
                            )
                            stats["errors"] += 1
                            await session.rollback()
                            continue

                    await asyncio.sleep(0.5)

            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Error syncing category %s (%s): %s",
                    category,
                    self.adapter.name,
                    e,
                )
                stats["errors"] += 1

        logger.debug("%s product sync completed. Stats: %s", self.adapter.name, stats)

        # Enqueue a single batch enrichment job if new products were created.
        # One job avoids flooding the Icecat API with thousands of individual requests.
        # The batch task's limit caps concurrent Icecat calls; remaining products
        # are picked up by the scheduled batch cron.
        if stats["new_products"] > 0:
            try:
                await trigger_batch_enrichment(limit=50)
                logger.info(
                    "Enqueued batch Icecat enrichment for %d new %s products",
                    stats["new_products"],
                    self.adapter.name,
                )
            except Exception as enrich_exc:  # noqa: BLE001
                logger.warning(
                    "Failed to enqueue batch Icecat enrichment after %s sync: %s",
                    self.adapter.name,
                    enrich_exc,
                )

        return stats
