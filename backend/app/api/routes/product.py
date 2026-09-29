import uuid
from collections.abc import Callable
from typing import Any, cast

from fastapi import Depends
from sqlmodel import col, not_, select

from app.api.base_router import BaseRouter
from app.api.deps import CurrentUser, SessionDep, get_current_user_optional
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.inventory.services.availability import publish_with_availability
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
from app.features.product.services.publication import (
    content_ready_condition,
    has_storefront_content,
    publication_blockers,
    publication_conditions,
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

    def generate_read_endpoint(self) -> Callable[..., Any]:
        """Override: 404 on public reads of products without storefront content."""

        async def read(
            session: SessionDep,
            id: uuid.UUID,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> ProductPublic:
            await self._check_auth(session, "read", current_user)
            try:
                record = await self.crud.read(session, id=id, user=current_user)
            except RecordNotFoundError:
                raise AppError(
                    code="product.not_found",
                    status_code=404,
                    message="Product not found",
                    details={"product_id": str(id), "reason": "record_not_found"},
                )

            is_admin = current_user is not None and current_user.is_superuser
            if not is_admin and not has_storefront_content(record):
                raise AppError(
                    code="product.not_found",
                    status_code=404,
                    message="Product not found",
                    details={"product_id": str(id), "reason": "not_enriched"},
                )

            if not is_admin:
                blockers = await publication_blockers(session, cast(Product, record))
                if blockers:
                    raise AppError(
                        code="product.not_found",
                        status_code=404,
                        message="Product not found",
                        details={
                            "product_id": str(id),
                            "reason": "not_publishable",
                            "blockers": blockers,
                        },
                    )

            return (await publish_with_availability(session, [record]))[0]

        read.__name__ = "get_one_product"
        return read

    def generate_read_multi_endpoint(self) -> Callable[..., Any]:
        """Override: public listing shows only products with storefront content."""

        async def read_multi(
            session: SessionDep,
            skip: int = 0,
            limit: int = 100,
            order_by: str | None = None,
            include_archived: bool = False,
            status: str | None = None,
            search: str | None = None,
            current_user: CurrentUser | None = Depends(get_current_user_optional),
        ) -> Any:
            await self._check_auth(session, "read", current_user)

            is_admin = current_user is not None and current_user.is_superuser
            statement = None
            if not is_admin:
                statement = select(Product).where(
                    col(Product.is_active).is_(True),
                    col(Product.is_admin_active).is_(True),
                    col(Product.parent_product_id).is_(None),
                    content_ready_condition(),
                    *publication_conditions(),
                )
            else:
                conditions: list[Any] = []
                if status == "active":
                    conditions.append(col(Product.is_active).is_(True))
                elif status == "enriched":
                    conditions.append(col(Product.is_enriched).is_(True))
                elif status == "inactive":
                    conditions.append(col(Product.is_active).is_(False))
                elif status == "hidden":
                    # Active but invisible on the storefront: waiting for
                    # Icecat, and not published as it stands by the admin.
                    conditions.append(col(Product.is_active).is_(True))
                    conditions.append(not_(content_ready_condition()))
                term = (search or "").strip()
                if term:
                    pattern = f"%{term}%"
                    conditions.append(
                        col(Product.name).ilike(pattern)
                        | col(Product.supplier_sku).ilike(pattern)
                        | col(Product.vendor_part_number).ilike(pattern)
                    )
                if conditions:
                    statement = (
                        select(Product)
                        .where(*conditions)
                        .order_by(col(Product.created_at))
                    )

            result = await self.crud.read_multi(
                session,
                statement=statement,
                skip=skip,
                limit=limit,
                filter=None,
                order_by=order_by,
                include_archived=include_archived,
                user=current_user,
            )
            return ProductsPublic(
                data=await publish_with_availability(session, result["data"]),
                count=result["count"],
            )

        read_multi.__name__ = "get_multiple_products"
        return read_multi


class Auth:
    """Represents auth."""

    read: bool = False
    create: bool = True
    update: bool = True
    delete: bool = True
    create_superuser: bool = True
    update_superuser: bool = True
    delete_superuser: bool = True


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
