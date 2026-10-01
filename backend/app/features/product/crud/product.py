# mypy: disable-error-code="arg-type,assignment,operator"

import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import String, and_, case, cast, func, literal, null, or_
from sqlalchemy import update as sa_update
from sqlalchemy.orm.attributes import set_committed_value
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.inventory.services.availability import (
    available_quantity_expression,
    local_stock_expression,
    supplier_stock_expression,
)
from app.features.product.models.price_history import (
    REASON_PRODUCT_WRITE,
    price_change_entry,
)
from app.features.product.models.product import (
    Product,
    ProductCreate,
    ProductUpdate,
)
from app.features.product.models.product_spec import ProductSpec
from app.features.product.services.identity import (
    gtin_variants,
    normalize_text_key,
    product_identity_key,
)
from app.features.product.services.pricing import (
    CurrencyRateMissing,
    PricingContext,
)
from app.features.product.services.publication import (
    content_ready_condition,
    publication_conditions,
)

logger = logging.getLogger(__name__)


def margin_values(context: PricingContext, product: Product) -> dict[str, Any]:
    """Cost price and margin to store next to ``sale_price_cached``."""
    try:
        figures = context.margin(product, product.sale_price_cached)
    except Exception as exc:  # noqa: BLE001 - never blocks a price write
        logger.warning("Margin not computed for product %s: %s", product.id, exc)
        figures = None
    return {
        "unit_cost_cached": figures.unit_cost if figures else None,
        "margin_cached": figures.margin_amount if figures else None,
        "margin_pct_cached": figures.margin_pct if figures else None,
    }


def stamp_margin(context: PricingContext, product: Product) -> None:
    for name, value in margin_values(context, product).items():
        setattr(product, name, value)


class ProductCrud(CrudBase[Product, ProductCreate, ProductUpdate]):
    """Represents product crud."""

    async def _apply_runtime_sale_prices(
        self,
        session: AsyncSession,
        products: list[Product],
    ) -> None:
        """Apply runtime pricing on top of persisted products.

        One :class:`PricingContext` per call: the referentials are loaded once
        and every price is computed in memory, whatever the number of rows.
        """
        if not products:
            return

        try:
            context = await PricingContext.for_session(session)
            for product in products:
                product.base_price = context.price(product)
        except CurrencyRateMissing:
            raise
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to apply runtime pricing: %s", exc)

    # -- materialized storefront price ----------------------------------------

    async def _stamp_cached_price(
        self, session: AsyncSession, record: Product | None
    ) -> None:
        """Materialize the storefront list price on a product being written.

        Runs before the caller's commit, so the cached price lands in the same
        transaction as the change that made it stale. A missing currency rate
        leaves it ``None`` (the product is not publishable anyway); any other
        failure is logged and never blocks the write.
        """
        if record is None:
            return
        if getattr(record, "has_variants", False):
            # The parent is never sold: its price and margin are the cheapest
            # variant's (« à partir de »), never computed from its own row.
            from app.features.product.services.variants import (
                refresh_parent_from_variants,
            )

            await refresh_parent_from_variants(session, record)
            return
        previous = record.sale_price_cached
        try:
            context = await PricingContext.for_session(session)
            record.sale_price_cached = context.price(record)
        except CurrencyRateMissing as exc:
            logger.warning(
                "Cached price left unset for product %s: %s",
                getattr(record, "id", None),
                exc,
            )
            record.sale_price_cached = None
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Cached price not refreshed for product %s: %s",
                getattr(record, "id", None),
                exc,
            )
            return
        record.sale_price_cached_at = datetime.now(timezone.utc)
        stamp_margin(context, record)
        entry = price_change_entry(
            record.id, previous, record.sale_price_cached, reason=REASON_PRODUCT_WRITE
        )
        if entry is not None:
            session.add(entry)

    async def after_create(
        self,
        session: AsyncSession,
        *,
        record: Product | None = None,
        data: Any,
        user: Any | None,
    ) -> None:
        """Materialize the list price of a freshly created product."""
        await self._stamp_cached_price(session, record)

    async def after_update(
        self,
        session: AsyncSession,
        *,
        data: Any,
        record: Product | None = None,
        id: uuid.UUID | None = None,
        user: Any | None,
    ) -> None:
        """Re-materialize the list price after any product update."""
        await self._stamp_cached_price(session, record)

    async def refresh_cached_prices(
        self,
        session: AsyncSession,
        products: list[Product],
        *,
        context: PricingContext,
        reason: str = "refresh",
    ) -> int:
        """Recompute ``sale_price_cached`` for ``products`` (no commit).

        Returns how many rows were priced; rows whose currency has no rate
        are set to ``None``. Every change is journaled under ``reason``.
        """
        now = datetime.now(timezone.utc)
        priced = 0
        for product in products:
            previous = product.sale_price_cached
            try:
                product.sale_price_cached = context.price(product)
                priced += 1
            except CurrencyRateMissing:
                product.sale_price_cached = None
            product.sale_price_cached_at = now
            stamp_margin(context, product)
            session.add(product)
            entry = price_change_entry(
                product.id, previous, product.sale_price_cached, reason=reason
            )
            if entry is not None:
                session.add(entry)
        return priced

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

    async def list_by_supplier_sku(
        self,
        session: AsyncSession,
        *,
        supplier_name: str,
        supplier_sku: str,
    ) -> list[Product]:
        """Every product of ``supplier_name`` carrying ``supplier_sku``, manual or not.

        Used by the sync resolution: a product typed by hand and linked to the
        supplier is a legitimate match for that supplier's import.
        """
        statement = select(Product).where(
            Product.supplier_name == supplier_name,
            Product.supplier_sku == supplier_sku,
        )
        result = await session.exec(statement)
        return list(result.all())

    async def find_by_identity(
        self,
        session: AsyncSession,
        *,
        supplier_name: str,
        ean: str | None = None,
        upc: str | None = None,
        manufacturer: str | None = None,
        vendor_part_number: str | None = None,
    ) -> tuple[list[Product], str | None]:
        """Candidates of ``supplier_name`` matching the item's identity keys.

        Two levels, the first that yields anything wins: the barcode (EAN /
        UPC, every equivalent writing, against both columns), then the
        manufacturer + manufacturer part number pair (case and surrounding
        spaces ignored). Returns ``(candidates, key)`` with ``key`` in
        ``"gtin"`` / ``"manufacturer_part"`` / ``None``. Inactive products
        are included: a delisted article that comes back must be recognised.
        """
        variants = gtin_variants(ean) | gtin_variants(upc)
        if variants:
            statement = select(Product).where(
                Product.supplier_name == supplier_name,
                or_(
                    func.trim(col(Product.ean)).in_(variants),
                    func.trim(col(Product.upc)).in_(variants),
                ),
            )
            rows = list((await session.exec(statement)).all())
            if rows:
                return rows, "gtin"

        maker = normalize_text_key(manufacturer)
        part = normalize_text_key(vendor_part_number)
        if maker and part:
            statement = select(Product).where(
                Product.supplier_name == supplier_name,
                func.lower(func.trim(col(Product.manufacturer))) == maker,
                func.lower(func.trim(col(Product.vendor_part_number))) == part,
            )
            rows = list((await session.exec(statement)).all())
            if rows:
                return rows, "manufacturer_part"

        return [], None

    @staticmethod
    def storefront_conditions() -> list[Any]:
        """SQL: what the storefront may show (active, with content, publishable)."""
        return [
            col(Product.is_active).is_(True),
            col(Product.is_admin_active).is_(True),
            # Variants are reached through their parent, never listed alone.
            col(Product.parent_product_id).is_(None),
            content_ready_condition(),
            *publication_conditions(),
        ]

    async def find_offers(
        self, session: AsyncSession, product: Product
    ) -> list[Product]:
        """Other storefront products that are the same physical item.

        Siblings across *all* suppliers (one product per source is the model:
        the customer compares them here), matched on the indexed
        ``identity_key`` (canonical barcode, else manufacturer + part number).
        Returns the siblings only, without runtime pricing.
        """
        key = getattr(product, "identity_key", None) or product_identity_key(product)
        if not key:
            return []
        statement = (
            select(Product)
            .where(
                col(Product.id) != product.id,
                col(Product.identity_key) == key,
                *self.storefront_conditions(),
            )
            .order_by(col(Product.created_at).asc())
        )
        return list((await session.exec(statement)).all())

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
                col(Product.parent_product_id).is_(None),
                content_ready_condition(),
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

    @staticmethod
    def _spec_condition(key: str, expected: Any) -> Any | None:
        """SQL for one ``specs`` filter, against the ``product_specs`` projection.

        ``<key>_min`` → ``value_numeric >= n``; ``<key>`` with a list or a
        scalar → ``value_text IN (...)`` (values are stored lowercased), or
        ``value_numeric ==`` when the value parses as a number.
        """
        key_text = str(key).strip().lower()
        if not key_text:
            return None

        if key_text.endswith("_min"):
            try:
                minimum = Decimal(str(expected))
            except Exception:  # noqa: BLE001
                return None
            spec_key = key_text[: -len("_min")]
            return (
                select(ProductSpec.id)
                .where(
                    col(ProductSpec.product_id) == col(Product.id),
                    col(ProductSpec.spec_key) == spec_key,
                    col(ProductSpec.value_numeric) >= minimum,
                )
                .exists()
            )

        values = (
            list(expected) if isinstance(expected, list | tuple | set) else [expected]
        )
        texts = [str(v).strip().lower() for v in values if str(v).strip()]
        if not texts:
            return None
        numbers: list[Decimal] = []
        for text in texts:
            try:
                numbers.append(Decimal(text))
            except Exception:  # noqa: BLE001
                continue
        value_match = col(ProductSpec.value_text).in_(texts)
        if numbers:
            value_match = or_(value_match, col(ProductSpec.value_numeric).in_(numbers))
        return (
            select(ProductSpec.id)
            .where(
                col(ProductSpec.product_id) == col(Product.id),
                col(ProductSpec.spec_key) == key_text,
                value_match,
            )
            .exists()
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
        stock: str | None = None,
        condition: str | None = None,
        limit: int = 24,
        offset: int = 0,
        group_offers: bool = True,
    ) -> dict[str, Any]:
        """Search products entirely in SQL: filters, grouping, page and facets.

        Prices come from ``sale_price_cached`` (materialized by the pricing
        service), so the price filter, the choice of the cheapest offer per
        ``identity_key`` and the facets are computed by the database; the
        cost of a search follows the page size, not the catalog size. Rows
        not yet priced (``NULL``) that land in the page are priced on the fly
        and persisted.

        With ``group_offers`` (the storefront default), a same physical item
        sold by several suppliers appears once, by its cheapest offer (in
        stock first at equal price); ``offers_counts`` tells how many offers
        each returned entry stands for.
        """
        conditions: list[Any] = list(self.storefront_conditions())

        query_text = (q or "").strip()
        rank_expr: Any = null()
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
            conditions.append(search_doc.op("@@")(ts_q))
            rank_expr = func.ts_rank(search_doc, ts_q)

        if category_id is not None:
            conditions.append(col(Product.category_id) == category_id)
        if manufacturer:
            conditions.append(
                col(Product.manufacturer).ilike(f"%{manufacturer.strip()}%")
            )
        # Sellable stock = warehouse + supplier, as the checkout counts it.
        if in_stock is True:
            conditions.append(available_quantity_expression() > 0)
        elif in_stock is False:
            conditions.append(available_quantity_expression() <= 0)
        # Where the stock is: our warehouse, or the supplier.
        if stock == "local":
            conditions.append(local_stock_expression() > 0)
        elif stock == "supplier":
            conditions.append(supplier_stock_expression() > 0)
        if condition:
            conditions.append(col(Product.condition) == condition)
        if price_min is not None:
            conditions.append(col(Product.sale_price_cached) >= price_min)
        if price_max is not None:
            conditions.append(col(Product.sale_price_cached) <= price_max)
        for key, expected in (specs or {}).items():
            condition = self._spec_condition(key, expected)
            if condition is not None:
                conditions.append(condition)

        group_key = func.coalesce(
            col(Product.identity_key), cast(col(Product.id), String)
        )
        offers_expr: Any = (
            func.count().over(partition_by=group_key) if group_offers else literal(1)
        )
        candidates: Any = select(
            col(Product.id).label("id"),
            rank_expr.label("rank"),
            offers_expr.label("offers_count"),
        ).where(*conditions)
        if group_offers:
            candidates = candidates.distinct(group_key).order_by(
                group_key,
                col(Product.sale_price_cached).asc().nulls_last(),
                (available_quantity_expression() > 0).desc(),
            )
        representatives = candidates.cte("representatives")

        total_count = int(
            (
                await session.exec(select(func.count()).select_from(representatives))
            ).one()
        )

        page_statement = (
            select(Product, representatives.c.offers_count)
            .join(representatives, representatives.c.id == col(Product.id))
            .order_by(
                representatives.c.rank.desc().nulls_last(),
                col(Product.created_at).desc(),
            )
            .offset(offset)
            .limit(limit)
        )
        page_rows = list((await session.exec(page_statement)).all())
        products: list[Product] = [row[0] for row in page_rows]
        offers_counts = {
            str(row[0].id): int(row[1]) for row in page_rows if int(row[1]) > 1
        }

        # Rows not priced yet: price them now (a page at most) and keep it.
        unpriced = [p for p in products if p.sale_price_cached is None]
        if unpriced:
            await self._price_and_persist_now(session, unpriced)
        for product in products:
            product.base_price = product.sale_price_cached or Decimal("0.00")

        facets = await self._search_facets(session, representatives)

        return {
            "data": products,
            "count": total_count,
            "facets": facets,
            "offers_counts": offers_counts,
        }

    async def _price_and_persist_now(
        self, session: AsyncSession, products: list[Product]
    ) -> None:
        """Fallback for rows whose ``sale_price_cached`` is still ``NULL``.

        Prices them with the session's context and writes the result through a
        separate connection, so the caller's transaction and its loaded
        instances are left untouched (a commit here would expire the whole
        page). The instances get the values as already-committed state.
        """
        try:
            context = await PricingContext.for_session(session)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallback pricing unavailable: %s", exc)
            return
        now = datetime.now(timezone.utc)
        priced: dict[uuid.UUID, Decimal | None] = {}
        margins: dict[uuid.UUID, dict[str, Any]] = {}
        for product in products:
            try:
                priced[product.id] = context.price(product)
            except CurrencyRateMissing:
                priced[product.id] = None
            set_committed_value(product, "sale_price_cached", priced[product.id])
            set_committed_value(product, "sale_price_cached_at", now)
            margins[product.id] = margin_values(context, product)
            for name, value in margins[product.id].items():
                set_committed_value(product, name, value)

        bind = getattr(session, "bind", None)
        if bind is None or not hasattr(bind, "begin"):
            return
        try:
            async with bind.begin() as connection:
                for product_id, price in priced.items():
                    await connection.execute(
                        sa_update(Product)
                        .where(col(Product.id) == product_id)
                        .values(
                            sale_price_cached=price,
                            sale_price_cached_at=now,
                            **margins[product_id],
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Fallback prices not persisted: %s", exc)

    @staticmethod
    async def _search_facets(
        session: AsyncSession, representatives: Any
    ) -> dict[str, Any]:
        """Facets of the (grouped) result set, three aggregate queries."""
        clean_maker = func.nullif(func.trim(col(Product.manufacturer)), "")
        maker_key = func.lower(func.coalesce(clean_maker, "unknown"))
        maker_rows = (
            await session.exec(
                select(func.min(clean_maker), func.count())
                .select_from(Product)
                .join(representatives, representatives.c.id == col(Product.id))
                .group_by(maker_key)
            )
        ).all()
        manufacturers = {
            (row[0] if row[0] else "unknown"): int(row[1]) for row in maker_rows
        }

        category_rows = (
            await session.exec(
                select(col(Product.category_id), func.count())
                .select_from(Product)
                .join(representatives, representatives.c.id == col(Product.id))
                .group_by(col(Product.category_id))
            )
        ).all()
        categories = {
            (str(row[0]) if row[0] is not None else "none"): int(row[1])
            for row in category_rows
        }

        price = func.coalesce(col(Product.sale_price_cached), Decimal("0"))
        bucket = case(
            (price < Decimal("50000"), "0-49999"),
            (price < Decimal("100000"), "50000-99999"),
            else_="100000+",
        )
        bucket_rows = (
            await session.exec(
                select(bucket, func.count())
                .select_from(Product)
                .join(representatives, representatives.c.id == col(Product.id))
                .group_by(bucket)
            )
        ).all()
        price_ranges = {"0-49999": 0, "50000-99999": 0, "100000+": 0}
        for row in bucket_rows:
            price_ranges[str(row[0])] = int(row[1])

        stock_row = (
            await session.exec(
                select(
                    func.count().filter(local_stock_expression() > 0),
                    func.count().filter(supplier_stock_expression() > 0),
                    func.count().filter(col(Product.condition) == "refurbished"),
                    func.count(),
                )
                .select_from(Product)
                .join(representatives, representatives.c.id == col(Product.id))
            )
        ).first()
        local_count, supplier_count, refurbished_count, total = (
            (int(v or 0) for v in stock_row) if stock_row else (0, 0, 0, 0)
        )

        return {
            "manufacturers": manufacturers,
            "categories": categories,
            "price_ranges": price_ranges,
            "stock": {"local": local_count, "supplier": supplier_count},
            "conditions": {
                "new": total - refurbished_count,
                "refurbished": refurbished_count,
            },
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
