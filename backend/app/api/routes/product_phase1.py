import uuid

from fastapi import APIRouter, HTTPException, Query, status

from app.api.deps import CurrentSuperUser, SessionDep
from app.features.base.crud import RecordNotFoundError
from app.features.product.crud.product import crud_product
from app.features.product.models.product import (
    ProductFeatureRequest,
    ProductPublic,
    ProductSearchFacets,
    ProductSearchRequest,
    ProductSearchResponse,
    ProductsPublic,
)

router = APIRouter(prefix="/product", tags=["product"])


@router.post("/search", response_model=ProductSearchResponse)
async def search_products(
    session: SessionDep,
    payload: ProductSearchRequest,
) -> ProductSearchResponse:
    """Search products with filters and return lightweight facets."""
    search_result = await crud_product.search_products(
        session=session,
        q=payload.q,
        category_id=payload.category_id,
        manufacturer=payload.manufacturer,
        price_min=payload.price_min,
        price_max=payload.price_max,
        specs=payload.specs,
        in_stock=payload.in_stock,
        limit=payload.limit,
        offset=payload.offset,
    )

    products = [
        ProductPublic.model_validate(product)
        for product in search_result.get("data", [])
    ]

    return ProductSearchResponse(
        data=products,
        count=search_result.get("count", 0),
        facets=ProductSearchFacets.model_validate(search_result.get("facets", {})),
    )


@router.get("/featured", response_model=ProductsPublic)
async def get_featured_products(
    session: SessionDep,
    limit: int = Query(default=10, ge=1, le=50),
) -> ProductsPublic:
    """Get public featured products."""
    products = await crud_product.get_featured(session=session, limit=limit)
    return ProductsPublic(
        data=[ProductPublic.model_validate(product) for product in products],
        count=len(products),
    )


@router.post("/{product_id}/feature", response_model=ProductPublic)
async def feature_product(
    product_id: uuid.UUID,
    payload: ProductFeatureRequest,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> ProductPublic:
    """Mark product as featured (admin only)."""
    try:
        product = await crud_product.set_featured(
            session=session,
            product_id=product_id,
            featured_position=payload.featured_position,
            featured_until=payload.featured_until,
            user=_current_user,
        )
    except RecordNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return ProductPublic.model_validate(product)


@router.delete("/{product_id}/feature", response_model=ProductPublic)
async def unfeature_product(
    product_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> ProductPublic:
    """Remove product from featured listing (admin only)."""
    try:
        product = await crud_product.clear_featured(
            session=session,
            product_id=product_id,
            user=_current_user,
        )
    except RecordNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Product not found")

    return ProductPublic.model_validate(product)
