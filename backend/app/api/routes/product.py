from app.api.base_router import BaseRouter
from app.features.product.crud.product import (
    ProductCrud,
    crud_product,
)
from app.features.product.models.product import (
    Product,
    ProductCreate,
    ProductPublic,
    ProductsPublic,
    ProductUpdate,
)


class ProductRouter(
    BaseRouter[
        Product,
        ProductCreate,
        ProductUpdate,
        ProductPublic,
        ProductsPublic,
        ProductCrud,
    ]
):
    """Represents product router."""

    pass


class Auth:
    """Represents auth."""

    read: bool = False
    create: bool = True
    update: bool = True
    delete: bool = True


router = ProductRouter(
    name="product",
    tags=["product"],
    crud=crud_product,
    schema_public=ProductPublic,
    schema_publics=ProductsPublic,
    schema_create=ProductCreate,
    schema_update=ProductUpdate,
    auth=Auth(),
    auto=True,
)
