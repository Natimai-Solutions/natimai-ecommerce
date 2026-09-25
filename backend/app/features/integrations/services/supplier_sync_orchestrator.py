"""
Supplier-agnostic synchronization orchestrator.

Owns application-level sync behavior, independent of which distributor is being
synced and of where the data comes from (a distributor API, a CSV/Excel file
the admin uploaded):
- mapping normalized supplier payloads to the local product schema
- upsert strategy by supplier identity (persisted mapping first, then
  ``supplier_sku`` + ``supplier_name``)
- transaction / commit strategy

Each :class:`~app.services.suppliers.base.SupplierAdapter` provides the catalog
and price/availability data; this class never talks to a vendor API directly.
"""

import asyncio
import logging
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.integrations.crud.supplier_sync import supplier_product_mapping_crud
from app.features.integrations.models.supplier_sync import SupplierProductMapping
from app.features.integrations.services.supplier_data_normalization import (
    DEFAULT_CURRENCY,
    evaluate_product_filters,
    normalize_supplier_snapshot,
)
from app.features.place.crud import crud_place
from app.features.product.crud.product import crud_product
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductCreate,
    ProductUpdate,
)
from app.features.product.services.overrides import merge_locks, strip_locked
from app.services.suppliers.base import NormalizedProductData, SupplierAdapter
from app.tasks.icecat_tasks import trigger_batch_enrichment

logger = logging.getLogger(__name__)


#: Match keys, from the most to the least authoritative.
MATCH_MAPPING = "mapping"
MATCH_SUPPLIER_SKU = "supplier_sku"
MATCH_GTIN = "gtin"
MATCH_MANUFACTURER_PART = "manufacturer_part"
MATCH_KEYS: tuple[str, ...] = (
    MATCH_MAPPING,
    MATCH_SUPPLIER_SKU,
    MATCH_GTIN,
    MATCH_MANUFACTURER_PART,
)

#: Content an admin typed on a manual product. When the sync adopts such a
#: product, these fields are locked (if filled) so the file never overwrites
#: what was written by hand; only the sourcing fields flow from the supplier.
#: Refurbished-lot fields a file import may carry (see FILE_MAPPING_TARGETS).
REFURB_ITEM_FIELDS: tuple[str, ...] = (
    "condition",
    "condition_grade",
    "battery_health_pct",
    "os_licence",
    "warranty_months",
    "availability_mode",
)

ADOPTION_CONTENT_FIELDS: tuple[str, ...] = (
    "name",
    "description",
    "long_description",
    "image_url",
    "pricing_mode",
    "base_price",
    "margin_rate_pct",
    "customs_rate_pct",
    "category_id",
    "tax_rate_id",
    "weight",
    "dimensions_length",
    "dimensions_width",
    "dimensions_height",
    "supplier_place_id",
)


def _empty_stats() -> dict[str, int]:
    return {
        "total_fetched": 0,
        "new_products": 0,
        "updated_products": 0,
        "adopted_products": 0,
        "ambiguous_products": 0,
        "skipped_products": 0,
        "filtered_products": 0,
        "errors": 0,
        **{f"matched_by_{key}": 0 for key in MATCH_KEYS},
    }


@dataclass(slots=True)
class Resolution:
    """Outcome of looking a supplier payload up in the local catalog."""

    product: Product | None = None
    mapping: SupplierProductMapping | None = None
    #: One of :data:`MATCH_KEYS`, ``None`` when nothing matched.
    match_key: str | None = None
    #: Several products of this supplier claim the same identity: refuse to
    #: guess, the row is reported instead of being written.
    ambiguous: bool = False
    candidates: list[str] = field(default_factory=list)

    @property
    def adopts_manual(self) -> bool:
        """The match is a product typed by hand and linked to this supplier."""
        return self.product is not None and not bool(
            getattr(self.product, "is_supplier_managed", False)
        )


def _is_filled(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, Decimal | int | float):
        return value != 0
    return True


def adoption_locks(product: Product) -> list[str]:
    """Locks to place on a manual product the sync is about to adopt.

    Every content field the admin filled is kept; ``pricing_mode`` is always
    kept (it is a decision, whatever its value). ``base_price`` only matters
    when it carries a fixed price.
    """
    locked: list[str] = ["pricing_mode"]
    for name in ADOPTION_CONTENT_FIELDS:
        if name == "pricing_mode":
            continue
        if _is_filled(getattr(product, name, None)):
            locked.append(name)
    return merge_locks(getattr(product, "overridden_fields", None), locked)


class SupplierSyncOrchestrator:
    """Application-level orchestrator for one supplier's sync workflows."""

    def __init__(self, adapter: SupplierAdapter) -> None:
        """Initialize the supplier sync orchestrator instance."""
        self.adapter = adapter
        # Origin place resolution is memoized per sync run (one DB lookup).
        self._origin_place_id: uuid.UUID | None = None
        self._origin_place_resolved = False

    async def _resolve_origin_place_id(self, session: AsyncSession) -> uuid.UUID | None:
        """Resolve the supplier's origin ``Place`` id.

        The supplier row's ``origin_place_id`` wins; the adapter's
        ``origin_place_code`` is the fallback (idempotent
        ``crud_place.get_by_code``). Memoized for the run. Returns ``None``
        when the supplier declares no origin or the code is unknown.
        """
        if self._origin_place_resolved:
            return self._origin_place_id

        place_id = getattr(self.adapter, "origin_place_id", None)
        if place_id is not None:
            self._origin_place_id = place_id
            self._origin_place_resolved = True
            return self._origin_place_id

        code = getattr(self.adapter, "origin_place_code", None)
        if code:
            place = await crud_place.get_by_code(session=session, code=code)
            if place is not None:
                self._origin_place_id = place.id
            else:
                logger.warning(
                    "Origin place code %r not found for supplier %s; "
                    "supplier_place_id left unset.",
                    code,
                    self.adapter.name,
                )
        self._origin_place_resolved = True
        return self._origin_place_id

    @property
    def supplier_name(self) -> str:
        """Execute supplier name."""
        return self.adapter.name

    @classmethod
    async def for_supplier(
        cls, session: AsyncSession, supplier_name: str
    ) -> "SupplierSyncOrchestrator":
        """Build an orchestrator for the API-backed supplier ``supplier_name``."""
        from app.services.suppliers import UnknownSupplierError, resolve_adapter

        adapter = await resolve_adapter(session, supplier_name)
        if adapter is None:
            raise UnknownSupplierError(supplier_name)
        return cls(adapter)

    def _default_pricing_mode(self) -> PricingMode:
        """Pricing mode stamped on products created from this supplier."""
        if getattr(self.adapter, "is_domestic", False):
            return PricingMode.DOMESTIC
        return PricingMode.IMPORT

    def _to_product_data(self, item: NormalizedProductData) -> dict[str, Any]:
        """Convert a normalized supplier payload into local product fields.

        Price and stock are only written when the payload carries them: the
        catalog endpoint of most distributors (Ingram in particular) returns
        neither, and zeroing the persisted values on every catalog sweep would
        blank the storefront until the next inventory sync. A file import, on
        the other hand, brings cost and stock along and they are applied as an
        inventory refresh would (``cost_amount`` included).

        ``is_active`` is intentionally not set here: the sync-threshold
        decision belongs to the inventory sync, where real pricing data is.
        """
        data: dict[str, Any] = {
            "name": item.name,
            "description": item.description
            or " ".join(filter(None, [item.manufacturer, item.name])),
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
            "is_supplier_managed": True,
            "upc": item.upc,
            "ean": item.ean,
        }
        # Refurbished-lot columns: only what the file carries, so a catalogue
        # without them never resets what the admin typed.
        for name in REFURB_ITEM_FIELDS:
            value = getattr(item, name, None)
            if value is not None:
                data[name] = value

        if item.price is not None or item.quantity is not None:
            currency = (
                item.currency
                or getattr(self.adapter, "price_currency", None)
                or DEFAULT_CURRENCY
            )
            snapshot = normalize_supplier_snapshot(
                raw_price=item.price if item.price is not None else 0,
                raw_quantity=item.quantity if item.quantity is not None else 0,
                raw_currency=currency,
            )
            if item.quantity is not None:
                data["supplier_quantity"] = snapshot.supplier_quantity
            if item.price is not None:
                data["supplier_price"] = snapshot.supplier_price
                data["supplier_price_currency"] = snapshot.supplier_price_currency
                data["cost_amount"] = snapshot.supplier_price
                data["cost_currency"] = snapshot.supplier_price_currency
            data["last_supplier_sync"] = datetime.now(timezone.utc)
            data["supplier_missing_since"] = None

        return data

    async def _resolve_existing_product(
        self, session: AsyncSession, item: NormalizedProductData
    ) -> Resolution:
        """Find the product this payload refers to, within this supplier only.

        Order, first unambiguous hit wins:

        1. the persisted mapping (supplier, SKU);
        2. a product of this supplier with the same SKU — synced *or* typed by
           hand and linked to the supplier (the latter is adopted);
        3. the barcode (EAN / UPC, equivalent writings) — a product whose
           supplier reference changed is still the same product;
        4. manufacturer + manufacturer part number.

        Products of another supplier are never matched: one product is one
        source, a same physical item stocked by two suppliers is two products
        and the customer picks the cheaper one.
        """
        mapping = await supplier_product_mapping_crud.get_by_supplier_sku(
            session=session,
            supplier_name=self.adapter.name,
            supplier_sku=item.supplier_sku,
        )

        if mapping is not None:
            mapped_product = await session.get(Product, mapping.local_product_id)
            if (
                mapped_product is not None
                and mapped_product.supplier_name == self.adapter.name
                and mapped_product.supplier_sku == item.supplier_sku
            ):
                return Resolution(
                    product=mapped_product, mapping=mapping, match_key=MATCH_MAPPING
                )

            logger.warning(
                "Supplier mapping mismatch for %s SKU %s (mapping_id=%s). "
                "Falling back to supplier identity.",
                self.adapter.name,
                item.supplier_sku,
                mapping.id,
            )

        by_sku = await crud_product.list_by_supplier_sku(
            session=session,
            supplier_name=self.adapter.name,
            supplier_sku=item.supplier_sku,
        )
        if by_sku:
            # Historical duplicates (a manual product next to the synced one):
            # the synced one keeps being the sync's target.
            managed = [p for p in by_sku if getattr(p, "is_supplier_managed", False)]
            pool = managed or by_sku
            if len(pool) > 1:
                return Resolution(
                    mapping=mapping,
                    match_key=MATCH_SUPPLIER_SKU,
                    ambiguous=True,
                    candidates=[str(p.id) for p in pool],
                )
            return Resolution(
                product=pool[0], mapping=mapping, match_key=MATCH_SUPPLIER_SKU
            )

        candidates, key = await crud_product.find_by_identity(
            session,
            supplier_name=self.adapter.name,
            ean=item.ean,
            upc=item.upc,
            manufacturer=item.manufacturer,
            vendor_part_number=item.vendor_part_number,
        )
        if len(candidates) > 1:
            return Resolution(
                mapping=mapping,
                match_key=key,
                ambiguous=True,
                candidates=[f"{p.supplier_sku or '?'} ({p.id})" for p in candidates],
            )
        if candidates:
            return Resolution(product=candidates[0], mapping=mapping, match_key=key)

        return Resolution(mapping=mapping)

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
            # Recognised under a new reference (barcode / manufacturer part):
            # re-key the row this product already has rather than adding one.
            mapping = await supplier_product_mapping_crud.get_by_product(
                session=session,
                supplier_name=self.adapter.name,
                local_product_id=product.id,
            )
            if mapping is not None:
                mapping.supplier_sku = item.supplier_sku
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

        resolution = await self._resolve_existing_product(session=session, item=item)
        if resolution.ambiguous:
            logger.warning(
                "Ambiguous match for %s SKU %s by %s: %s — row left untouched",
                self.adapter.name,
                item.supplier_sku,
                resolution.match_key,
                resolution.candidates,
            )
            return {
                "action": "ambiguous",
                "product_id": "",
                "match_key": resolution.match_key or "",
                "error": (
                    f"plusieurs articles de ce fournisseur portent la même "
                    f"identité ({resolution.match_key}) : "
                    + ", ".join(resolution.candidates)
                ),
            }
        existing_product = resolution.product

        product_data_dict = self._to_product_data(item)

        # Adopting a product typed by hand: what the admin wrote stays theirs
        # (locked), the supplier brings reference, cost and stock.
        adopted = resolution.adopts_manual
        if adopted and existing_product is not None:
            product_data_dict["overridden_fields"] = adoption_locks(existing_product)

        # Stamp the supplier's origin place (drives the logistics first leg),
        # but never clobber a manual admin override: set it only when creating a
        # product or when the existing one has no origin yet. Omitting the key
        # leaves the persisted value untouched (partial update semantics).
        if existing_product is None or existing_product.supplier_place_id is None:
            origin_place_id = await self._resolve_origin_place_id(session)
            if origin_place_id is not None:
                product_data_dict["supplier_place_id"] = origin_place_id

        # The pricing mode follows the supplier's customs regime at creation;
        # afterwards it is the admin's (a domestic product can be re-priced
        # as fixed, and the admin edit locks the field).
        if existing_product is None:
            product_data_dict["pricing_mode"] = self._default_pricing_mode()

        # Resolve internal category from supplier_subcategory (get_or_create)
        if item.subcategory:
            from app.features.product.crud.category import crud_category

            category, _created = await crud_category.get_or_create_by_name(
                session, name=item.subcategory
            )
            product_data_dict["category_id"] = category.id

        if filter_action == "deactivate":
            logger.debug(
                "Deactivating product %s (%s) — matched a 'deactivate' filter rule (subcategory=%s)",
                item.supplier_sku,
                self.adapter.name,
                item.subcategory,
            )
            product_data_dict["is_active"] = False

        # Respect admin overrides: never overwrite fields the admin has locked.
        # Omitting them from the update dict preserves the persisted values.
        if existing_product is not None:
            locks = product_data_dict.get(
                "overridden_fields", existing_product.overridden_fields
            )
            product_data_dict = strip_locked(product_data_dict, locks)
            if adopted:
                product_data_dict["overridden_fields"] = locks

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
            "action": "adopted" if adopted else action,
            "product_id": str(product.id),
            "match_key": resolution.match_key or "",
        }

    async def preview_items(
        self,
        session: AsyncSession,
        items: Iterable[NormalizedProductData],
        *,
        sample_size: int = 20,
    ) -> tuple[dict[str, int], list[dict[str, Any]]]:
        """Resolve a batch without writing anything (import dry run).

        Returns the counters the real import would produce for the
        resolution step (new / updated / adopted / ambiguous, and by which
        key) plus the first ``sample_size`` rows detailed.
        """
        counts = {
            "new": 0,
            "updated": 0,
            "adopted": 0,
            "ambiguous": 0,
            "skipped": 0,
            **{f"matched_by_{key}": 0 for key in MATCH_KEYS},
        }
        rows: list[dict[str, Any]] = []

        for item in items:
            row: dict[str, Any] = {
                "supplier_sku": item.supplier_sku,
                "name": item.name,
                "action": "new",
                "match_key": None,
                "product_id": None,
                "product_name": None,
                "message": None,
            }
            if not item.supplier_sku or not item.name:
                row["action"] = "skipped"
                row["message"] = "référence ou désignation vide"
                counts["skipped"] += 1
            else:
                resolution = await self._resolve_existing_product(session, item)
                if resolution.ambiguous:
                    row["action"] = "ambiguous"
                    row["match_key"] = resolution.match_key
                    row["message"] = "plusieurs articles candidats : " + ", ".join(
                        resolution.candidates
                    )
                    counts["ambiguous"] += 1
                elif resolution.product is not None:
                    row["action"] = "adopted" if resolution.adopts_manual else "updated"
                    row["match_key"] = resolution.match_key
                    row["product_id"] = str(resolution.product.id)
                    row["product_name"] = getattr(resolution.product, "name", None)
                    counts[row["action"]] += 1
                    if resolution.match_key:
                        counts[f"matched_by_{resolution.match_key}"] += 1
                else:
                    counts["new"] += 1
            if len(rows) < sample_size:
                rows.append(row)

        return counts, rows

    async def sync_items(
        self,
        session: AsyncSession,
        items: Iterable[NormalizedProductData],
        *,
        stats: dict[str, int] | None = None,
        errors: list[dict[str, str]] | None = None,
    ) -> dict[str, int]:
        """Upsert a batch of normalized products, one commit per product.

        Shared by the API catalog sync and the file import. A failure on one
        product is logged, counted and rolled back; the batch goes on. When
        ``errors`` is given, each failure is appended as ``{sku, error}``.
        """
        if stats is None:
            stats = _empty_stats()

        for item in items:
            stats["total_fetched"] += 1
            if not item.supplier_sku or not item.name:
                stats["skipped_products"] += 1
                continue
            try:
                result = await self.upsert_product(session, item)
                action = result["action"]
                if action == "filtered":
                    stats["filtered_products"] += 1
                    continue
                if action == "ambiguous":
                    stats["ambiguous_products"] += 1
                    if errors is not None:
                        errors.append(
                            {"sku": item.supplier_sku, "error": result["error"]}
                        )
                    continue
                if action == "created":
                    stats["new_products"] += 1
                elif action == "adopted":
                    stats["adopted_products"] += 1
                elif action == "updated":
                    stats["updated_products"] += 1
                match_key = result.get("match_key")
                if match_key:
                    stats[f"matched_by_{match_key}"] += 1
                await session.commit()
            except Exception as e:  # noqa: BLE001
                logger.error(
                    "Error syncing product %s (%s): %s",
                    item.supplier_sku,
                    self.adapter.name,
                    e,
                )
                stats["errors"] += 1
                if errors is not None:
                    errors.append({"sku": item.supplier_sku, "error": str(e)})
                await session.rollback()
                continue

        return stats

    async def _enqueue_enrichment(self, new_products: int) -> None:
        """Enqueue one batch Icecat enrichment job when products were created.

        One job avoids flooding the Icecat API with thousands of individual
        requests. The batch task's limit caps concurrent Icecat calls;
        remaining products are picked up by the scheduled batch cron.
        """
        if new_products <= 0:
            return
        try:
            await trigger_batch_enrichment(limit=50)
            logger.info(
                "Enqueued batch Icecat enrichment for %d new %s products",
                new_products,
                self.adapter.name,
            )
        except Exception as enrich_exc:  # noqa: BLE001
            logger.warning(
                "Failed to enqueue batch Icecat enrichment after %s sync: %s",
                self.adapter.name,
                enrich_exc,
            )

    async def import_items(
        self,
        session: AsyncSession,
        items: list[NormalizedProductData],
        *,
        errors: list[dict[str, str]] | None = None,
    ) -> dict[str, int]:
        """Import an already-normalized list (file import): upsert + enrichment."""
        stats = await self.sync_items(session, items, errors=errors)
        logger.info("%s file import completed. Stats: %s", self.adapter.name, stats)
        await self._enqueue_enrichment(stats["new_products"])
        return stats

    async def sync_products_to_database(
        self, session: AsyncSession, categories: list[str] | None = None
    ) -> dict[str, int]:
        """Synchronize the supplier catalog into the local database.

        Commits incrementally (one product per commit) so a failure mid-run
        does not roll back already-imported products.
        """
        sync_categories = list(categories or self.adapter.default_categories)
        stats = _empty_stats()

        logger.debug(
            "Starting %s product sync for categories: %s",
            self.adapter.name,
            sync_categories,
        )

        for category in sync_categories:
            try:
                async for page in self.adapter.fetch_catalog(category=category):
                    await self.sync_items(session, page, stats=stats)
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
        await self._enqueue_enrichment(stats["new_products"])
        return stats
