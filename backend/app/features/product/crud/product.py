# mypy: disable-error-code="arg-type,assignment,operator"

from datetime import datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.product.models.product import (
    Product,
    ProductCreate,
    ProductUpdate,
)


class ProductCrud(CrudBase[Product, ProductCreate, ProductUpdate]):
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
        """
        conditions = [
            Product.supplier_sku == supplier_sku,
            col(Product.is_active).is_(True),
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
        from datetime import datetime, timedelta

        threshold_time = datetime.utcnow() - timedelta(hours=hours_threshold)
        threshold_iso = threshold_time.isoformat()

        conditions = [
            col(Product.is_supplier_managed).is_(True),
            col(Product.is_active).is_(True),
            (col(Product.last_supplier_sync).is_(None))
            | (Product.last_supplier_sync < threshold_iso),
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
            sync_time = datetime.utcnow()

        product = await session.get(self.model, product_id)
        if not product:
            return None

        product.last_supplier_sync = sync_time.isoformat()
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


crud_product = ProductCrud(
    model=Product,
    schema_create=ProductCreate,
    schema_update=ProductUpdate,
    order_by=col(Product.created_at),
)
