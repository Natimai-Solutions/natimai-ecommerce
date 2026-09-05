# mypy: disable-error-code="arg-type,assignment,operator"

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.product.models.product import (
    Product,
    ProductCreate,
    ProductUpdate,
)
from app.features.product.services.pricing import (
    CurrencyRateMissing,
    calculate_sale_price,
    resolve_default_price_group,
)
from app.features.product.services.publication import publication_conditions
from app.features.shipping.services.origin import (
    load_origin_context,
    resolve_product_origin_regime,
)

logger = logging.getLogger(__name__)
_DECIMAL_PATTERN = re.compile(r"[-+]?\d*\.?\d+")


class ProductCrud(CrudBase[Product, ProductCreate, ProductUpdate]):
    """Represents product crud."""

    async def _apply_runtime_sale_prices(
        self,
        session: AsyncSession,
        products: list[Product],
    ) -> None:
        """Apply runtime pricing on top of persisted products."""
        if not products:
            return

        try:
            default_group = await resolve_default_price_group(session)
            origin_context = await load_origin_context(session)
            for product in products:
                product.base_price = await calculate_sale_price(
                    session,
                    product,
                    group=default_group,
                    origin_regime=await resolve_product_origin_regime(
                        session, product, context=origin_context
                    ),
                )
        except CurrencyRateMissing:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to apply runtime pricing: %s", exc)

    @staticmethod
    def _extract_max_decimal(values: list[str]) -> Decimal | None:
        """Extract maximum decimal from a list of string values."""
        max_value: Decimal | None = None
        for value in values:
            for match in _DECIMAL_PATTERN.findall(value):
                try:
                    parsed = Decimal(match)
                except Exception:  # noqa: BLE001
                    continue
                if max_value is None or parsed > max_value:
                    max_value = parsed
        return max_value

    @staticmethod
    def _matches_specs(product: Product, specs: dict[str, Any]) -> bool:
        """Evaluate lightweight specs filters against stored Icecat payload."""
        if not specs:
            return True

        raw_specs = product.technical_specifications or []
        specs_text = json.dumps(raw_specs, ensure_ascii=False).lower()

        flat_specs: dict[str, list[str]] = {}
        for item in raw_specs:
            if not isinstance(item, dict):
                continue
            for key, value in item.items():
                key_text = str(key).strip().lower()
                if not key_text:
                    continue
                flat_specs.setdefault(key_text, []).append(str(value).lower())

            label = item.get("name") or item.get("label") or item.get("feature")
            value = item.get("value") or item.get("presentation_value")
            if label is not None and value is not None:
                label_text = str(label).strip().lower()
                if label_text:
                    flat_specs.setdefault(label_text, []).append(str(value).lower())

        for key, expected in specs.items():
            key_text = str(key).strip().lower()
            if not key_text:
                continue

            values_for_key: list[str] = []
            for candidate_key, candidate_values in flat_specs.items():
                if candidate_key == key_text or key_text in candidate_key:
                    values_for_key.extend(candidate_values)

            if key_text.endswith("_min"):
                base_key = key_text[: -len("_min")]
                values_for_min: list[str] = []
                for candidate_key, candidate_values in flat_specs.items():
                    if candidate_key == base_key or base_key in candidate_key:
                        values_for_min.extend(candidate_values)
                if not values_for_min:
                    values_for_min = [specs_text]

                try:
                    min_expected = Decimal(str(expected))
                except Exception:  # noqa: BLE001
                    continue

                max_found = ProductCrud._extract_max_decimal(values_for_min)
                if max_found is None or max_found < min_expected:
                    return False
                continue

            haystack = " ".join(values_for_key).strip() or specs_text
            if isinstance(expected, list | tuple | set):
                expected_values = [str(value).lower() for value in expected]
                if not any(value in haystack for value in expected_values):
                    return False
                continue

            expected_text = str(expected).lower().strip()
            if expected_text and expected_text not in haystack:
                return False

        return True

    @staticmethod
    def _build_search_facets(products: list[Product]) -> dict[str, dict[str, int]]:
        """Build lightweight facets from filtered products."""
        # Group manufacturers case-insensitively so "HP Inc." and "HP INC." map
        # to a single facet. Key on casefold; keep the first-seen spelling as the
        # display label exposed to the storefront.
        manufacturer_counts: dict[str, int] = {}
        manufacturer_labels: dict[str, str] = {}
        categories: dict[str, int] = {}
        price_ranges = {
            "0-49999": 0,
            "50000-99999": 0,
            "100000+": 0,
        }

        for product in products:
            manufacturer = (product.manufacturer or "unknown").strip() or "unknown"
            mfr_key = manufacturer.casefold()
            manufacturer_counts[mfr_key] = manufacturer_counts.get(mfr_key, 0) + 1
            manufacturer_labels.setdefault(mfr_key, manufacturer)

            category_key = str(product.category_id) if product.category_id else "none"
            categories[category_key] = categories.get(category_key, 0) + 1

            if product.base_price < Decimal("50000"):
                price_ranges["0-49999"] += 1
            elif product.base_price < Decimal("100000"):
                price_ranges["50000-99999"] += 1
            else:
                price_ranges["100000+"] += 1

        manufacturers = {
            manufacturer_labels[key]: count
            for key, count in manufacturer_counts.items()
        }

        return {
            "manufacturers": manufacturers,
            "categories": categories,
            "price_ranges": price_ranges,
        }

    async def read(
        self,
        session: AsyncSession,
        *,
        id: uuid.UUID,
        user: Any | None = None,
        read_event: bool = False,
    ) -> Product | Any:
        """Read one product and apply runtime pricing."""
        record = await super().read(
            session,
            id=id,
            user=user,
            read_event=read_event,
        )
        if isinstance(record, Product):
            await self._apply_runtime_sale_prices(session, [record])
        return record

    async def read_multi(
        self,
        session: AsyncSession,
        *,
        statement: Any | None = None,
        skip: int = 0,
        limit: int = 0,
        ids: list[uuid.UUID] | None = None,
        include_archived: bool = False,
        filter: Any = None,
        order_by: Any | None = None,
        user: Any | None = None,
        read_event: bool = False,
    ) -> dict[str, Any]:
        """Read multiple products and apply runtime pricing."""
        result = await super().read_multi(
            session,
            statement=statement,
            skip=skip,
            limit=limit,
            ids=ids,
            include_archived=include_archived,
            filter=filter,
            order_by=order_by,
            user=user,
            read_event=read_event,
        )
        data = result.get("data", [])
        if isinstance(data, list) and data:
            await self._apply_runtime_sale_prices(session, data)
        return result

    async def get_by_supplier_sku(
        self,
        session: AsyncSession,
        supplier_sku: str,
        supplier_name: str | None = None,
        supplier_managed_only: bool = True,
    ) -> Product | None:
        """Get a product by supplier identity.

        By default, only supplier-managed products are returned to avoid
        accidentally mutating manual products during supplier sync jobs.

        Note: ``is_active`` is intentionally NOT filtered here. Sync jobs must
        be able to re-find products that were previously deactivated (e.g.
        below sync thresholds) so they can re-activate them when pricing or
        availability comes back into bounds.
        """
        conditions = [
            Product.supplier_sku == supplier_sku,
        ]

        if supplier_managed_only:
            conditions.append(col(Product.is_supplier_managed).is_(True))

        if supplier_name:
            conditions.append(Product.supplier_name == supplier_name)

        statement = select(Product).where(*conditions)
        result = await session.exec(statement)
        return result.first()

    async def get_supplier_products(
        self,
        session: AsyncSession,
        supplier_name: str,
        category: str | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[Product]:
        """Get all products from a specific supplier, optionally filtered by category"""
        conditions = [
            Product.supplier_name == supplier_name,
            col(Product.is_supplier_managed).is_(True),
            col(Product.is_active).is_(True),
        ]

        if category:
            conditions.append(Product.supplier_category == category)

        statement = (
            select(Product)
            .where(*conditions)
            .order_by(col(Product.created_at).desc())
            .limit(limit)
            .offset(offset)
        )

        result = await session.exec(statement)
        return list(result.all())

    async def get_products_needing_sync(
        self,
        session: AsyncSession,
        supplier_name: str | None = None,
        hours_threshold: int = 24,
    ) -> list[Product]:
        """Get supplier products that need synchronization (old or never synced)"""
        threshold_time = datetime.now(timezone.utc) - timedelta(hours=hours_threshold)

        conditions = [
            col(Product.is_supplier_managed).is_(True),
            col(Product.is_active).is_(True),
            (col(Product.last_supplier_sync).is_(None))
            | (Product.last_supplier_sync < threshold_time),
        ]

        if supplier_name:
            conditions.append(Product.supplier_name == supplier_name)

        statement = select(Product).where(*conditions)

        result = await session.exec(statement)
        return list(result.all())

    async def update_supplier_sync_time(
        self,
        session: AsyncSession,
        product_id: str,
        sync_time: datetime | None = None,
    ) -> Product | None:
        """Update the last sync time for a supplier product"""
        if sync_time is None:
            sync_time = datetime.now(timezone.utc)

        product = await session.get(self.model, product_id)
        if not product:
            return None

        product.last_supplier_sync = sync_time
        session.add(product)
        await session.commit()
        await session.refresh(product)

        return product

    async def get_by_vendor_part_number(
        self,
        session: AsyncSession,
        vendor_part_number: str,
        manufacturer: str | None = None,
    ) -> Product | None:
        """Get a product by vendor part number and optionally manufacturer"""
        conditions = [
            Product.vendor_part_number == vendor_part_number,
            col(Product.is_active).is_(True),
        ]

        if manufacturer:
            conditions.append(Product.manufacturer == manufacturer)

        statement = select(Product).where(*conditions)
        result = await session.exec(statement)
        return result.first()

    async def get_featured(
        self,
        session: AsyncSession,
        *,
        limit: int = 10,
    ) -> list[Product]:
        """Get featured products ordered by explicit position first."""
        now = datetime.now(timezone.utc)
        statement = (
            select(Product)
            .where(
                col(Product.is_active).is_(True),
                col(Product.is_admin_active).is_(True),
                col(Product.is_enriched).is_(True),
                col(Product.is_featured).is_(True),
                (
                    col(Product.featured_until).is_(None)
                    | (Product.featured_until >= now)
                ),
                *publication_conditions(),
            )
            .order_by(
                col(Product.featured_position).is_(None),
                col(Product.featured_position).asc(),
                col(Product.created_at).desc(),
            )
            .limit(limit)
        )
        result = await session.exec(statement)
        products = list(result.all())
        await self._apply_runtime_sale_prices(session, products)
        return products

    async def set_featured(
        self,
        session: AsyncSession,
        *,
        product_id: uuid.UUID,
        featured_position: int | None = None,
        featured_until: datetime | None = None,
        user: Any | None = None,
    ) -> Product:
        """Mark a product as featured."""
        product = await self.read(session, id=product_id, user=user)
        return await self.update(
            session,
            id=product_id,
            record=product,
            data={
                "is_featured": True,
                "featured_position": featured_position,
                "featured_until": featured_until,
            },
            user=user,
        )

    async def clear_featured(
        self,
        session: AsyncSession,
        *,
        product_id: uuid.UUID,
        user: Any | None = None,
    ) -> Product:
        """Remove featured flag from a product."""
        product = await self.read(session, id=product_id, user=user)
        return await self.update(
            session,
            id=product_id,
            record=product,
            data={
                "is_featured": False,
                "featured_position": None,
                "featured_until": None,
            },
            user=user,
        )

    async def search_products(
        self,
        session: AsyncSession,
        *,
        q: str | None = None,
        category_id: uuid.UUID | None = None,
        manufacturer: str | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        specs: dict[str, Any] | None = None,
        in_stock: bool | None = None,
        limit: int = 24,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Search products with runtime pricing and lightweight facets."""
        statement = select(Product).where(
            col(Product.is_active).is_(True),
            col(Product.is_admin_active).is_(True),
            col(Product.is_enriched).is_(True),
            *publication_conditions(),
        )

        query_text = (q or "").strip()
        _ts_rank: Any | None = None
        if query_text:
            # GIN FTS path — expression matches ix_products_search_fts exactly.
            # Uses `||` (IMMUTABLE) instead of concat_ws (STABLE) so the same
            # expression can also be used in the index definition.
            search_text = (
                func.coalesce(col(Product.name), "")
                .op("||")(" ")
                .op("||")(func.coalesce(col(Product.description), ""))
                .op("||")(" ")
                .op("||")(func.coalesce(col(Product.manufacturer), ""))
                .op("||")(" ")
                .op("||")(func.coalesce(col(Product.vendor_part_number), ""))
            )
            search_doc = func.to_tsvector("simple", search_text)
            ts_q = func.plainto_tsquery("simple", query_text)
            statement = statement.where(search_doc.op("@@")(ts_q))
            _ts_rank = func.ts_rank(search_doc, ts_q)

        if category_id is not None:
            statement = statement.where(Product.category_id == category_id)

        if manufacturer:
            statement = statement.where(
                col(Product.manufacturer).ilike(f"%{manufacturer.strip()}%")
            )

        if in_stock is True:
            statement = statement.where(Product.supplier_quantity > Decimal("0"))
        elif in_stock is False:
            statement = statement.where(Product.supplier_quantity <= Decimal("0"))

        if _ts_rank is not None:
            statement = statement.order_by(
                _ts_rank.desc(), col(Product.created_at).desc()
            )
        else:
            statement = statement.order_by(col(Product.created_at).desc())
        result = await session.exec(statement)
        products = list(result.all())
        await self._apply_runtime_sale_prices(session, products)

        requested_specs = specs or {}
        filtered_products: list[Product] = []
        for product in products:
            if price_min is not None and product.base_price < price_min:
                continue
            if price_max is not None and product.base_price > price_max:
                continue
            if not self._matches_specs(product, requested_specs):
                continue
            filtered_products.append(product)

        total_count = len(filtered_products)
        paginated_products = filtered_products[offset : offset + limit]
        facets = self._build_search_facets(filtered_products)

        return {
            "data": paginated_products,
            "count": total_count,
            "facets": facets,
        }


crud_product = ProductCrud(
    model=Product,
    schema_create=ProductCreate,
    schema_update=ProductUpdate,
    order_by=col(Product.created_at),
    default_filter=and_(
        col(Product.is_active).is_(True),
        col(Product.is_admin_active).is_(True),
    ),
    outbox_events={
        "create": "create.product",
        "update": "update.product",
        "delete": "delete.product",
    },
)
