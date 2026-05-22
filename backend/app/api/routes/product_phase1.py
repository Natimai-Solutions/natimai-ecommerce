import uuid
from decimal import Decimal

from fastapi import APIRouter, HTTPException, Query, status
from sqlmodel import col, func, select

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
from app.features.product.models.product_spec import (
    CategorySpecFacetsResponse,
    ProductSpec,
    SpecFacet,
    SpecFacetValue,
)
from app.features.product.services.spec_projection import get_spec_definitions

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Product not found"
        )

    return ProductPublic.model_validate(product)


@router.get("/categories/{category_id}/spec-facets", response_model=CategorySpecFacetsResponse)
async def get_category_spec_facets(
    category_id: uuid.UUID,
    session: SessionDep,
) -> CategorySpecFacetsResponse:
    """Return available spec facets (with value counts) for a category.

    Used by the storefront to build dynamic filter panels.
    Only returns specs that have at least one value for active enriched products
    in this category.
    """
    spec_defs = get_spec_definitions()

    # All spec keys applicable to any category (we filter by presence in the data)
    all_keys = [s["key"] for s in spec_defs]
    key_to_def = {s["key"]: s for s in spec_defs}

    # Fetch value distribution from product_specs for this category's enriched products
    from app.features.product.models.product import Product

    # enum facets: group by (spec_key, value_text)
    text_stmt = (
        select(
            ProductSpec.spec_key,
            ProductSpec.value_text,
            func.count(ProductSpec.product_id).label("cnt"),
        )
        .join(Product, Product.id == ProductSpec.product_id)
        .where(
            ProductSpec.spec_key.in_(all_keys),
            col(ProductSpec.value_text).is_not(None),
            Product.category_id == category_id,
            col(Product.is_active).is_(True),
            col(Product.is_enriched).is_(True),
        )
        .group_by(ProductSpec.spec_key, ProductSpec.value_text)
        .order_by(ProductSpec.spec_key, col(func.count(ProductSpec.product_id)).desc())
    )

    # numeric facets: group by (spec_key, value_numeric)
    numeric_stmt = (
        select(
            ProductSpec.spec_key,
            ProductSpec.value_numeric,
            func.count(ProductSpec.product_id).label("cnt"),
        )
        .join(Product, Product.id == ProductSpec.product_id)
        .where(
            ProductSpec.spec_key.in_(all_keys),
            col(ProductSpec.value_numeric).is_not(None),
            Product.category_id == category_id,
            col(Product.is_active).is_(True),
            col(Product.is_enriched).is_(True),
        )
        .group_by(ProductSpec.spec_key, ProductSpec.value_numeric)
        .order_by(ProductSpec.spec_key, ProductSpec.value_numeric)
    )

    text_result = await session.exec(text_stmt)
    numeric_result = await session.exec(numeric_stmt)

    # Aggregate into spec facets
    facets_by_key: dict[str, SpecFacet] = {}

    for row in text_result.all():
        key = row.spec_key
        if key not in facets_by_key and key in key_to_def:
            d = key_to_def[key]
            facets_by_key[key] = SpecFacet(
                key=key,
                label_fr=d["label_fr"],
                type=d["type"],
                unit=d.get("unit"),
                values=[],
            )
        if key in facets_by_key:
            facets_by_key[key].values.append(
                SpecFacetValue(value_text=row.value_text, count=row.cnt)
            )

    for row in numeric_result.all():
        key = row.spec_key
        if key not in facets_by_key and key in key_to_def:
            d = key_to_def[key]
            facets_by_key[key] = SpecFacet(
                key=key,
                label_fr=d["label_fr"],
                type=d["type"],
                unit=d.get("unit"),
                values=[],
            )
        if key in facets_by_key:
            facets_by_key[key].values.append(
                SpecFacetValue(value_numeric=Decimal(str(row.value_numeric)), count=row.cnt)
            )

    # Preserve YAML order
    ordered_facets = [
        facets_by_key[key] for key in all_keys if key in facets_by_key
    ]

    return CategorySpecFacetsResponse(
        category_id=category_id,
        specs=ordered_facets,
    )
