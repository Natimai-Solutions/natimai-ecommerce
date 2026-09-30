import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, Query, Response
from sqlmodel import Field, SQLModel, col, func, select

from app.api.deps import CurrentSuperUser, SessionDep, get_current_user_optional
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.integrations.models.supplier import Supplier
from app.features.inventory.services.availability import (
    local_quantities,
    publish_with_availability,
    supplier_available_quantity,
)
from app.features.product.crud.product import crud_product
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductFeatureRequest,
    ProductOfferPublic,
    ProductOffersResponse,
    ProductPublic,
    ProductSearchFacets,
    ProductSearchRequest,
    ProductSearchResponse,
    ProductsPublic,
)
from app.features.product.models.product_spec import (
    CategorySpecFacetsResponse,
    ProductKeySpecsResponse,
    ProductSpec,
    SpecFacet,
    SpecFacetValue,
)
from app.features.product.services.identity import product_identity_key
from app.features.product.services.key_specs import compute_key_specs
from app.features.product.services.popularity import (
    DEFAULT_LIMIT,
    DEFAULT_WINDOW_DAYS,
    MAX_LIMIT,
    MAX_WINDOW_DAYS,
    popular_products,
    record_product_view,
)
from app.features.product.services.pricing import (
    CurrencyRateMissing,
    PricingContext,
    calculate_price_by_mode,
    resolve_default_price_group,
    resolve_pricing_mode,
)
from app.features.product.services.publication import (
    content_ready_condition,
    has_storefront_content,
    publication_blockers,
)
from app.features.product.services.spec_projection import (
    get_effective_spec_definitions,
)
from app.features.product.services.variants import list_variants, option_axes
from app.features.shipping.models.route import ShippingRoute
from app.features.user.crud.user_preference import get_preference_for_user
from app.features.user.models.user import User

router = APIRouter(prefix="/product", tags=["product"])


# ---------------------------------------------------------------------------
# Shipping-modes response models
# ---------------------------------------------------------------------------


class ShippingModePricePublic(SQLModel):
    """Per-service-level price breakdown returned by the shipping-modes endpoint."""

    route_id: str
    service_level: str | None
    customer_label: str | None
    freight: Decimal
    sale_price: Decimal
    eta_days: int | None
    carbon_footprint_kg_co2e: float | None


class ProductShippingModesResponse(SQLModel):
    """Shipping-modes payload for a product detail page."""

    product_id: uuid.UUID
    shipping_modes: list[ShippingModePricePublic]
    default_mode: str | None


@router.get("/{product_id}/shipping-modes", response_model=ProductShippingModesResponse)
async def get_product_shipping_modes(
    product_id: uuid.UUID,
    session: SessionDep,
    current_user: object = Depends(get_current_user_optional),
) -> ProductShippingModesResponse:
    """Return per-service-level pricing for a product.

    The response contains one entry per active import route (service_level != null),
    sorted by priority then by is_default_import. The frontend uses this list to
    build the shipping-mode dropdown and switch sale prices locally without a
    refetch. The backend recalculates at checkout (authoritative).

    - Anonymous / no preference: use ``default_mode`` to pre-select.
    - Logged-in: client stores preference in ``localStorage`` or user profile.
    """
    try:
        product = await crud_product.read(session, id=product_id, user=current_user)
    except RecordNotFoundError:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Product not found",
            details={"product_id": str(product_id)},
        )

    is_admin = getattr(current_user, "is_superuser", False)
    if not is_admin and not has_storefront_content(product):
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Product not found",
            details={"product_id": str(product_id), "reason": "not_enriched"},
        )

    if not is_admin:
        blockers = await publication_blockers(session, product)
        if blockers:
            raise AppError(
                code="product.not_found",
                status_code=404,
                message="Product not found",
                details={
                    "product_id": str(product_id),
                    "reason": "not_publishable",
                    "blockers": blockers,
                },
            )

    # Load import routes ordered by priority asc (highest priority first = lowest number)
    route_stmt = (
        select(ShippingRoute)
        .where(col(ShippingRoute.service_level).is_not(None))
        .order_by(
            col(ShippingRoute.priority).asc(),
            col(ShippingRoute.is_default_import).desc(),
        )
    )
    route_result = await session.exec(route_stmt)
    import_routes = list(route_result.all())

    if not import_routes:
        return ProductShippingModesResponse(
            product_id=product_id,
            shipping_modes=[],
            default_mode=None,
        )

    group = await resolve_default_price_group(session)
    mode_prices = await calculate_price_by_mode(
        session, product, import_routes, group=group
    )

    # Resolve default_mode: user preference > is_default_import route > first route
    available_levels = {m.service_level for m in mode_prices if m.service_level}
    user_pref_mode: str | None = None
    if isinstance(current_user, User):
        pref = await get_preference_for_user(session, user_id=current_user.id)
        if pref and pref.preferred_shipping_mode in available_levels:
            user_pref_mode = pref.preferred_shipping_mode

    if user_pref_mode:
        default_mode: str | None = user_pref_mode
    else:
        default_route = next((r for r in import_routes if r.is_default_import), None)
        default_mode = (
            default_route.service_level
            if default_route is not None
            else (mode_prices[0].service_level if mode_prices else None)
        )

    return ProductShippingModesResponse(
        product_id=product_id,
        shipping_modes=[
            ShippingModePricePublic(
                route_id=m.route_id,
                service_level=m.service_level,
                customer_label=m.customer_label,
                freight=m.freight,
                sale_price=m.sale_price,
                eta_days=m.eta_days,
                carbon_footprint_kg_co2e=m.carbon_footprint_kg_co2e,
            )
            for m in mode_prices
        ],
        default_mode=default_mode,
    )


async def _load_published_product(
    session: SessionDep, product_id: uuid.UUID, current_user: object
) -> Product:
    """The product as the storefront may show it: 404 when missing or unpublished.

    Admins see unpublished products too (preview from the back office).
    """
    try:
        product = await crud_product.read(session, id=product_id, user=current_user)
    except RecordNotFoundError:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Product not found",
            details={"product_id": str(product_id)},
        )

    is_admin = getattr(current_user, "is_superuser", False)
    if not is_admin and (
        not has_storefront_content(product)
        or await publication_blockers(session, product)
    ):
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Product not found",
            details={"product_id": str(product_id), "reason": "not_publishable"},
        )
    return product


@router.get("/{product_id}/offers", response_model=ProductOffersResponse)
async def get_product_offers(
    product_id: uuid.UUID,
    session: SessionDep,
    current_user: object = Depends(get_current_user_optional),
) -> ProductOffersResponse:
    """Every storefront offer of the same physical item, current product included.

    One product is one source: the same item stocked by two suppliers is two
    products, and this is where the customer compares them. Siblings are
    found by barcode (EAN / UPC), else by manufacturer + part number.

    Prices are what the product page shows by default: for import-mode
    products, the default import route's freight is included; local and
    fixed-price products carry no import leg.
    """
    product = await _load_published_product(session, product_id, current_user)

    siblings = await crud_product.find_offers(session, product)
    everyone = [product, *siblings]

    default_route = (
        await session.exec(
            select(ShippingRoute)
            .where(
                col(ShippingRoute.is_default_import).is_(True),
                col(ShippingRoute.is_active).is_(True),
            )
            .limit(1)
        )
    ).first()
    context = await PricingContext.for_session(session)

    codes = {p.supplier_name for p in everyone if p.supplier_name}
    suppliers: dict[str, Supplier] = {}
    if codes:
        rows = await session.exec(select(Supplier).where(col(Supplier.code).in_(codes)))
        suppliers = {row.code: row for row in rows.all()}

    # Sellable stock as the checkout counts it: warehouse + supplier.
    local = await local_quantities(session, (p.id for p in everyone))

    offers: list[ProductOfferPublic] = []
    for candidate in everyone:
        mode = resolve_pricing_mode(candidate)
        route = default_route if mode is PricingMode.IMPORT else None
        try:
            sale_price = context.price(candidate, import_route=route)
        except CurrencyRateMissing:
            # No rate for the cost currency: shown as unpriced, sorted last.
            sale_price = Decimal("0")
        supplier = suppliers.get(candidate.supplier_name or "")
        quantity = Decimal(str(candidate.supplier_quantity or 0))
        local_quantity = local.get(candidate.id, Decimal("0.00"))
        available = local_quantity + supplier_available_quantity(candidate)
        offers.append(
            ProductOfferPublic(
                product_id=candidate.id,
                name=candidate.name,
                is_current=candidate.id == product.id,
                supplier_name=candidate.supplier_name,
                supplier_label=supplier.name if supplier is not None else None,
                is_domestic=(
                    supplier.is_domestic
                    if supplier is not None
                    else mode is not PricingMode.IMPORT
                ),
                pricing_mode=mode,
                sale_price=sale_price,
                supplier_quantity=quantity,
                local_quantity=local_quantity,
                available_quantity=available,
                in_stock=available > 0,
                image_url=candidate.image_url or candidate.supplier_image_url,
            )
        )

    # Cheapest priced offer first; a priced offer beats an unpriced one and,
    # at equal price, the one in stock.
    offers.sort(key=lambda o: (o.sale_price <= 0, o.sale_price, not o.in_stock, o.name))
    cheapest = next((o for o in offers if o.sale_price > 0), None)

    return ProductOffersResponse(
        product_id=product.id,
        identity_key=product_identity_key(product),
        offers=offers,
        cheapest_product_id=cheapest.product_id if cheapest is not None else None,
    )


@router.get("/{product_id}/key-specs", response_model=ProductKeySpecsResponse)
async def get_product_key_specs(
    product_id: uuid.UUID,
    session: SessionDep,
    current_user: object = Depends(get_current_user_optional),
) -> ProductKeySpecsResponse:
    """Up to four key-spec tiles for the product page (processeur, mémoire…).

    Driven by ``highlight_rank`` on the spec definitions; only specs the
    product has a projected value for are returned.
    """
    product = await _load_published_product(session, product_id, current_user)
    return ProductKeySpecsResponse(
        product_id=product_id, specs=await compute_key_specs(session, product)
    )


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
        condition=payload.condition.value if payload.condition else None,
        limit=payload.limit,
        offset=payload.offset,
        group_offers=payload.group_offers,
    )

    offers_counts: dict[str, int] = search_result.get("offers_counts", {}) or {}
    products = await publish_with_availability(session, search_result.get("data", []))
    for public in products:
        public.offers_count = offers_counts.get(str(public.id), 1)

    return ProductSearchResponse(
        data=products,
        count=search_result.get("count", 0),
        facets=ProductSearchFacets.model_validate(search_result.get("facets", {})),
    )


class ProductVariantsResponse(SQLModel):
    """The variants of a parent product and the option axes that tell them apart."""

    parent_id: uuid.UUID
    axes: list[str] = Field(default_factory=list)
    variants: list[ProductPublic] = Field(default_factory=list)


@router.get("/{product_id}/variants", response_model=ProductVariantsResponse)
async def get_product_variants(
    session: SessionDep,
    product_id: uuid.UUID,
    current_user: object = Depends(get_current_user_optional),
) -> ProductVariantsResponse:
    """Active variants of a product, with their price and sellable stock.

    Empty for a plain product. Variants are reached only through here (or by
    id): the listings show the parent.
    """
    product = await session.get(Product, product_id)
    is_admin = getattr(current_user, "is_superuser", False)
    if product is None or (not is_admin and not has_storefront_content(product)):
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Product not found",
            details={"product_id": str(product_id)},
        )
    variants = await list_variants(session, product_id)
    if not is_admin:
        variants = [v for v in variants if has_storefront_content(v)]
    await crud_product._apply_runtime_sale_prices(session, variants)  # noqa: SLF001
    return ProductVariantsResponse(
        parent_id=product_id,
        axes=option_axes(variants),
        variants=await publish_with_availability(session, variants),
    )


@router.get("/popular", response_model=ProductsPublic)
async def get_popular_products(
    session: SessionDep,
    days: int = Query(default=DEFAULT_WINDOW_DAYS, ge=1, le=MAX_WINDOW_DAYS),
    limit: int = Query(default=DEFAULT_LIMIT, ge=1, le=MAX_LIMIT),
) -> ProductsPublic:
    """Most viewed products over the last ``days`` days (storefront-visible only)."""
    products = await popular_products(
        session,
        conditions=crud_product.storefront_conditions(),
        days=days,
        limit=limit,
    )
    await crud_product._apply_runtime_sale_prices(session, products)  # noqa: SLF001
    return ProductsPublic(
        data=await publish_with_availability(session, products),
        count=len(products),
    )


@router.post("/{product_id}/view", status_code=204)
async def track_product_view(
    session: SessionDep,
    product_id: uuid.UUID,
) -> Response:
    """Count one view of a product page (anonymous, fire-and-forget).

    Only products the storefront shows are counted; anything else answers the
    same 204 so the endpoint reveals nothing about hidden rows.
    """
    product = await session.get(Product, product_id)
    if product is not None and product.is_active and product.is_admin_active:
        await record_product_view(session, product_id=product_id)
    return Response(status_code=204)


@router.get("/featured", response_model=ProductsPublic)
async def get_featured_products(
    session: SessionDep,
    limit: int = Query(default=10, ge=1, le=50),
) -> ProductsPublic:
    """Get public featured products."""
    products = await crud_product.get_featured(session=session, limit=limit)
    return ProductsPublic(
        data=await publish_with_availability(session, products),
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
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Product not found",
            details={"product_id": str(product_id)},
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
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Product not found",
            details={"product_id": str(product_id)},
        )

    return ProductPublic.model_validate(product)


@router.get(
    "/categories/{category_id}/spec-facets", response_model=CategorySpecFacetsResponse
)
async def get_category_spec_facets(
    category_id: uuid.UUID,
    session: SessionDep,
) -> CategorySpecFacetsResponse:
    """Return available spec facets (with value counts) for a category.

    Used by the storefront to build dynamic filter panels.
    Only returns specs that have at least one value for active enriched products
    in this category.
    """
    # DB-first definitions (admin edits to labels/units + activation are honoured);
    # inactive specs are excluded by the DB query, falling back to YAML if unseeded.
    spec_defs = await get_effective_spec_definitions(session)

    # All spec keys applicable to any category (we filter by presence in the data)
    all_keys = [s["key"] for s in spec_defs]
    key_to_def = {s["key"]: s for s in spec_defs}

    # Fetch value distribution from product_specs for this category's enriched products
    from app.features.product.models.product import Product

    # enum facets: group by (spec_key, value_text)
    text_stmt = (
        select(
            col(ProductSpec.spec_key),
            col(ProductSpec.value_text),
            func.count(col(ProductSpec.product_id)).label("cnt"),
        )
        .join(Product, col(Product.id) == col(ProductSpec.product_id))
        .where(
            col(ProductSpec.spec_key).in_(all_keys),
            col(ProductSpec.value_text).is_not(None),
            col(Product.category_id) == category_id,
            col(Product.is_active).is_(True),
            content_ready_condition(),
        )
        .group_by(col(ProductSpec.spec_key), col(ProductSpec.value_text))
        .order_by(
            col(ProductSpec.spec_key),
            func.count(col(ProductSpec.product_id)).desc(),
        )
    )

    # numeric facets: group by (spec_key, value_numeric)
    numeric_stmt = (
        select(
            col(ProductSpec.spec_key),
            col(ProductSpec.value_numeric),
            func.count(col(ProductSpec.product_id)).label("cnt"),
        )
        .join(Product, col(Product.id) == col(ProductSpec.product_id))
        .where(
            col(ProductSpec.spec_key).in_(all_keys),
            col(ProductSpec.value_numeric).is_not(None),
            col(Product.category_id) == category_id,
            col(Product.is_active).is_(True),
            content_ready_condition(),
        )
        .group_by(col(ProductSpec.spec_key), col(ProductSpec.value_numeric))
        .order_by(col(ProductSpec.spec_key), col(ProductSpec.value_numeric))
    )

    text_result = await session.exec(text_stmt)
    numeric_result = await session.exec(numeric_stmt)

    # Aggregate into spec facets.
    # Row access uses positional indices — mypy cannot infer named-tuple attributes
    # from multi-column select() results with SQLModel's session.exec().
    facets_by_key: dict[str, SpecFacet] = {}

    for text_row in text_result.all():
        key: str = text_row[0]  # spec_key
        value_text: str | None = text_row[1]  # value_text
        cnt_text: int = text_row[2]  # cnt
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
                SpecFacetValue(value_text=value_text, count=cnt_text)
            )

    for num_row in numeric_result.all():
        key = num_row[0]  # spec_key
        value_numeric_raw = num_row[1]  # value_numeric
        cnt_num: int = num_row[2]  # cnt
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
                SpecFacetValue(
                    value_numeric=Decimal(str(value_numeric_raw)), count=cnt_num
                )
            )

    # Preserve YAML order
    ordered_facets = [facets_by_key[key] for key in all_keys if key in facets_by_key]

    return CategorySpecFacetsResponse(
        category_id=category_id,
        specs=ordered_facets,
    )
