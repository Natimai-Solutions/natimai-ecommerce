from sqlmodel import func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.product.models.product import (
    Product,
    ProductCreate,
    ProductUpdate,
)


class ProductCrud(CrudBase[Product, ProductCreate, ProductUpdate]):
    pass

crud_product = ProductCrud(
    model=Product,
    schema_create=ProductCreate,
    schema_update=ProductUpdate,
    order_by=Product.created_at,
)
