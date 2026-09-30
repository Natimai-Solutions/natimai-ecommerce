"""Admin endpoints: create manual products and edit products with sync-safe overrides.

Editing a product here records every edited field in ``Product.overridden_fields``
so a later supplier sync or Icecat enrichment will not overwrite the admin's
values (rule in ``product/services/overrides.py``). Manual products
(``is_supplier_managed=False``) are never synced, so their overrides are moot but
recorded uniformly. A lock can be released field by field: the supplier value
then comes back with the next sync/enrichment, it is not restored on the spot.

A manual product may be linked to a declared supplier (``supplier_name`` =
``Supplier.code``): the supplier's origin warehouse and customs regime then
fill ``supplier_place_id`` and ``pricing_mode`` unless the payload sets them.
"""

from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.integrations.models.supplier import Supplier
from app.features.inventory.services.availability import publish_with_availability
from app.features.product.crud.product import crud_product
from app.features.product.models.price_history import (
    ProductPriceEntry,
    ProductPriceEntryPublic,
)
from app.features.product.models.product import (
    PricingMode,
    Product,
    ProductCreate,
    ProductPublic,
    ProductUpdate,
)
from app.features.product.services.overrides import merge_locks, release_lock
from app.features.product.services.pricing import CurrencyRateMissing, PricingContext
from app.features.product.services.variants import (
    list_variants,
    option_axes,
    refresh_parent_from_variants,
    variant_display_name,
)
from app.services.suppliers import load_supplier

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/products", tags=["admin-product"])


async def _resolve_supplier(session: SessionDep, code: str | None) -> Supplier | None:
    """Load the supplier a payload points at (404 when the code is unknown)."""
    if not code:
        return None
    supplier = await load_supplier(session, code, include_inactive=True)
    if supplier is None:
        raise AppError(
            code="supplier.not_found",
            status_code=404,
            message=f"Unknown supplier '{code}'",
            details={"supplier_name": code},
        )
    return supplier


def _apply_supplier_defaults(data: dict[str, Any], supplier: Supplier | None) -> None:
    """Fill origin and pricing mode from the supplier when the payload is silent."""
    if supplier is None:
        return
    if "supplier_place_id" not in data and supplier.origin_place_id is not None:
        data["supplier_place_id"] = supplier.origin_place_id
    if "pricing_mode" not in data:
        data["pricing_mode"] = (
            PricingMode.DOMESTIC if supplier.is_domestic else PricingMode.IMPORT
        )


class ProductPublishRequest(BaseModel):
    """Publish (or unpublish) products as they stand, without Icecat."""

    product_ids: list[uuid.UUID] = Field(..., min_length=1, max_length=500)
    published: bool = Field(
        default=True,
        description="True: show on the storefront as is; False: back to waiting",
    )


class ProductPublishResponse(BaseModel):
    """Outcome of a bulk publication."""

    updated: int
    missing: list[uuid.UUID] = Field(default_factory=list)


@router.post("/publish", response_model=ProductPublishResponse)
async def admin_publish_products(
    session: SessionDep,
    current_user: CurrentSuperUser,
    payload: ProductPublishRequest,
) -> ProductPublishResponse:
    """Show products on the storefront without waiting for Icecat enrichment.

    The storefront hides a supplier-synced row until Icecat has enriched it.
    An item Icecat does not know (a file import without barcode, a local
    brand) would stay hidden forever: this flag publishes it as it stands.
    Enrichment still runs later and only adds to it. Manual products are
    always visible and are left untouched here.
    """
    actor_id = current_user.id
    wanted = list(dict.fromkeys(payload.product_ids))
    rows = (
        await session.exec(select(Product).where(col(Product.id).in_(wanted)))
    ).all()
    found = {row.id for row in rows}
    for row in rows:
        row.published_without_enrichment = payload.published
        session.add(row)
    await session.commit()
    logger.info(
        "Admin %s set published_without_enrichment=%s on %d products",
        actor_id,
        payload.published,
        len(rows),
    )
    return ProductPublishResponse(
        updated=len(rows), missing=[pid for pid in wanted if pid not in found]
    )


@router.post("", response_model=ProductPublic)
async def admin_create_product(
    session: SessionDep,
    current_user: CurrentSuperUser,
    payload: ProductCreate,
) -> ProductPublic:
    """Create a manually-managed product (never overwritten by the supplier sync)."""
    data = payload.model_dump(exclude_unset=True)
    supplier = await _resolve_supplier(session, data.get("supplier_name"))
    _apply_supplier_defaults(data, supplier)
    create_data = ProductCreate.model_validate({**data, "is_supplier_managed": False})
    product = await crud_product.create(
        session=session, data=create_data, user=current_user
    )
    return ProductPublic.model_validate(product)


class PublishDraftsRequest(BaseModel):
    """Drafts to publish (unknown ids are ignored, reported in ``missing``)."""

    product_ids: list[uuid.UUID] = Field(min_length=1, max_length=500)


class PublishDraftsResponse(BaseModel):
    published: int = 0
    already_published: int = 0
    missing: list[uuid.UUID] = Field(default_factory=list)


class MarginPreviewRequest(BaseModel):
    """Price inputs of the product form, as they stand (unsaved)."""

    #: Existing product: its other fields (supplier place, weight…) apply.
    product_id: uuid.UUID | None = None
    pricing_mode: PricingMode | None = None
    base_price: Decimal | None = Field(default=None, ge=0)
    cost_amount: Decimal | None = Field(default=None, ge=0)
    cost_currency: str | None = Field(default=None, max_length=8)
    margin_rate_pct: Decimal | None = None
    customs_rate_pct: Decimal | None = Field(default=None, ge=0)
    tax_rate_id: uuid.UUID | None = None
    category_id: uuid.UUID | None = None


class MarginPreview(BaseModel):
    """What one unit sells for, what it costs and what is left."""

    price_incl_tax: Decimal | None
    tax_rate_pct: Decimal
    price_excl_tax: Decimal | None
    tax_amount: Decimal | None
    commission_amount: Decimal | None
    unit_cost: Decimal | None
    margin_amount: Decimal | None
    #: Margin / price excl. tax (taux de marque).
    margin_pct: Decimal | None
    #: Margin / cost (taux de marge).
    markup_pct: Decimal | None
    currency: str
    #: Why a figure is missing (no cost, no exchange rate…).
    note: str | None = None


@router.post("/margin-preview", response_model=MarginPreview)
async def preview_margin(
    payload: MarginPreviewRequest,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> MarginPreview:
    """Price, cost price and margin of the form's values, before saving."""
    fields: dict[str, Any] = {}
    if payload.product_id is not None:
        existing = await session.get(Product, payload.product_id)
        if existing is None:
            raise AppError(
                code="product.not_found",
                status_code=404,
                message="Product not found",
                details={"product_id": str(payload.product_id)},
            )
        fields = existing.model_dump()
    fields.update(payload.model_dump(exclude={"product_id"}, exclude_unset=True))
    fields.pop("id", None)
    fields.setdefault("name", "aperçu")
    # A transient row, never added to the session.
    draft = Product.model_validate(fields)
    if draft.cost_currency is None:
        draft.cost_currency = settings.REFERENCE_CURRENCY

    context = await PricingContext.load(session)
    tax_pct = context.tax_rate_pct(draft)
    empty = MarginPreview(
        price_incl_tax=None,
        tax_rate_pct=tax_pct,
        price_excl_tax=None,
        tax_amount=None,
        commission_amount=None,
        unit_cost=None,
        margin_amount=None,
        margin_pct=None,
        markup_pct=None,
        currency=settings.REFERENCE_CURRENCY,
    )
    try:
        price = context.price(draft)
    except CurrencyRateMissing as exc:
        return empty.model_copy(update={"note": f"Pas de taux de change pour {exc}"})
    figures = context.margin(draft, price)
    if figures is None:
        return empty.model_copy(
            update={
                "price_incl_tax": price,
                "note": "Saisissez le coût d'achat pour voir la marge.",
            }
        )
    return MarginPreview(
        price_incl_tax=figures.price_incl_tax,
        tax_rate_pct=figures.tax_rate_pct,
        price_excl_tax=figures.price_excl_tax,
        tax_amount=figures.tax_amount,
        commission_amount=figures.commission_amount,
        unit_cost=figures.unit_cost,
        margin_amount=figures.margin_amount,
        margin_pct=figures.margin_pct,
        markup_pct=figures.markup_pct,
        currency=settings.REFERENCE_CURRENCY,
        note=(
            "Vendu à perte : le prix HT ne couvre pas le coût de revient."
            if figures.margin_amount < 0
            else None
        ),
    )


@router.post("/publish-drafts", response_model=PublishDraftsResponse)
async def admin_publish_drafts(
    session: SessionDep,
    current_user: CurrentSuperUser,
    payload: PublishDraftsRequest,
) -> PublishDraftsResponse:
    """Take products out of draft. Publication then follows the usual gates
    (active, enriched, priceable): nothing else is forced here."""
    actor_id = current_user.id
    ids = list(dict.fromkeys(payload.product_ids))
    result = await session.exec(select(Product).where(col(Product.id).in_(ids)))
    found = {p.id: p for p in result.all()}
    response = PublishDraftsResponse(missing=[i for i in ids if i not in found])
    for product in found.values():
        if not product.is_draft:
            response.already_published += 1
            continue
        product.is_draft = False
        session.add(product)
        response.published += 1
    await session.commit()
    logger.info("Admin %s published %d draft product(s)", actor_id, response.published)
    return response


@router.get("/{product_id}/price-history", response_model=list[ProductPriceEntryPublic])
async def admin_product_price_history(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    limit: int = 50,
) -> list[ProductPriceEntryPublic]:
    """The product's price journal, newest first: every change of the
    storefront price with what caused it."""
    result = await session.exec(
        select(ProductPriceEntry)
        .where(ProductPriceEntry.product_id == product_id)
        .order_by(col(ProductPriceEntry.created_at).desc())
        .limit(max(1, min(limit, 500)))
    )
    return [ProductPriceEntryPublic.model_validate(e) for e in result.all()]


@router.put("/{product_id}", response_model=ProductPublic)
async def admin_update_product(
    session: SessionDep,
    current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    payload: ProductUpdate,
) -> ProductPublic:
    """Update a product and lock the edited fields against the supplier sync.

    Every content field present in the payload is added to ``overridden_fields``.
    """
    try:
        product = await crud_product.read(session=session, id=product_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        ) from exc

    changed = payload.model_dump(exclude_unset=True)
    if "supplier_name" in changed and changed["supplier_name"] != product.supplier_name:
        supplier = await _resolve_supplier(session, changed["supplier_name"])
        # Re-linking a manual product to another supplier moves its origin
        # and customs regime along, unless the same payload sets them.
        if not product.is_supplier_managed:
            _apply_supplier_defaults(changed, supplier)
    merged = merge_locks(product.overridden_fields, changed)

    update_data: dict[str, Any] = {**changed, "overridden_fields": merged}
    updated = await crud_product.update(
        session=session,
        id=product_id,
        data=update_data,
        user=current_user,
        record=product,
    )
    await _refresh_parent_of(session, updated)
    return ProductPublic.model_validate(updated)


async def _refresh_parent_of(session: SessionDep, product: Product) -> None:
    """A variant changed (price, activity): the parent's « à partir de » follows."""
    parent_id = getattr(product, "parent_product_id", None)
    if parent_id is None:
        return
    parent = await session.get(Product, parent_id)
    if parent is None:
        return
    await refresh_parent_from_variants(session, parent)
    await session.commit()


@router.delete("/{product_id}/overrides/{field}", response_model=ProductPublic)
async def admin_release_override(
    session: SessionDep,
    current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    field: str,
) -> ProductPublic:
    """Release one field lock so the supplier/enrichment value can come back.

    The current (admin) value stays until the next sync or enrichment rewrites
    it — no supplier copy is kept alongside.
    """
    try:
        product = await crud_product.read(session=session, id=product_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        ) from exc

    if field not in (product.overridden_fields or []):
        raise AppError(
            code="product.override.not_locked",
            status_code=404,
            message=f"Field '{field}' is not locked on this product",
            details={"product_id": str(product_id), "field": field},
        )

    updated = await crud_product.update(
        session=session,
        id=product_id,
        data={"overridden_fields": release_lock(product.overridden_fields, field)},
        user=current_user,
        record=product,
    )
    return ProductPublic.model_validate(updated)


# -- variants ------------------------------------------------------------------


class VariantCreateRequest(BaseModel):
    """A new variant of a parent product.

    Everything not given is inherited from the parent (category, tax rate,
    pricing mode, cost currency, margin and customs rates, supplier, origin,
    weight, description). The name is composed from the parent's and the
    option values unless ``name`` is set.
    """

    options: dict[str, str] = Field(..., min_length=1, max_length=10)
    name: str | None = Field(default=None, max_length=100)
    supplier_sku: str | None = Field(default=None, max_length=100)
    vendor_part_number: str | None = Field(default=None, max_length=100)
    ean: str | None = Field(default=None, max_length=32)
    base_price: Decimal | None = Field(default=None, ge=0)
    cost_amount: Decimal | None = Field(default=None, ge=0)
    supplier_quantity: Decimal | None = Field(default=None, ge=0)
    image_url: str | None = None
    weight: float | None = Field(default=None, ge=0)


class ProductVariantsAdminResponse(BaseModel):
    """Variants of a parent for the back office (inactive ones included)."""

    parent_id: uuid.UUID
    axes: list[str] = Field(default_factory=list)
    variants: list[ProductPublic] = Field(default_factory=list)


_INHERITED_FIELDS = (
    "description",
    "long_description",
    "pricing_mode",
    "cost_currency",
    "margin_rate_pct",
    "customs_rate_pct",
    "supplier_name",
    "supplier_place_id",
    "manufacturer",
    "weight",
    "dimensions_length",
    "dimensions_width",
    "dimensions_height",
    "tax_rate_id",
    "category_id",
    "is_enriched",
    "published_without_enrichment",
)


async def _load_parent(session: SessionDep, product_id: uuid.UUID) -> Product:
    try:
        parent = await crud_product.read(session=session, id=product_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        ) from exc
    if parent.parent_product_id is not None:
        raise AppError(
            code="product.variant.nested",
            status_code=409,
            message="A variant cannot have variants of its own",
            details={"product_id": str(product_id)},
        )
    return parent


@router.get("/{product_id}/variants", response_model=ProductVariantsAdminResponse)
async def admin_list_variants(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    product_id: uuid.UUID,
) -> ProductVariantsAdminResponse:
    """Every variant of a product, active or not."""
    parent = await _load_parent(session, product_id)
    variants = await list_variants(session, parent.id, include_inactive=True)
    return ProductVariantsAdminResponse(
        parent_id=parent.id,
        axes=option_axes(variants),
        variants=await publish_with_availability(session, variants),
    )


@router.post("/{product_id}/variants", response_model=ProductPublic)
async def admin_create_variant(
    session: SessionDep,
    current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    payload: VariantCreateRequest,
) -> ProductPublic:
    """Add a variant: a manual product row under the parent, which becomes
    the storefront entry (``has_variants``) and shows the cheapest price."""
    parent = await _load_parent(session, product_id)
    options = {k.strip(): v.strip() for k, v in payload.options.items() if k.strip()}
    if not options or any(not v for v in options.values()):
        raise AppError(
            code="product.variant.options_invalid",
            status_code=400,
            message="Each option needs a name and a value",
            details={"options": payload.options},
        )
    existing = await list_variants(session, parent.id, include_inactive=True)
    if any((v.variant_options or {}) == options and v.is_active for v in existing):
        raise AppError(
            code="product.variant.duplicate",
            status_code=409,
            message="A variant with these options already exists",
            details={"options": options},
        )

    data: dict[str, Any] = {
        field: getattr(parent, field) for field in _INHERITED_FIELDS
    }
    data.update(
        {
            "name": (payload.name or variant_display_name(parent.name, options))[:100],
            "parent_product_id": parent.id,
            "variant_options": options,
            "has_variants": False,
            "is_supplier_managed": False,
            "supplier_sku": payload.supplier_sku,
            "vendor_part_number": payload.vendor_part_number,
            "ean": payload.ean,
            "base_price": (
                payload.base_price
                if payload.base_price is not None
                else parent.base_price
            ),
            "cost_amount": (
                payload.cost_amount
                if payload.cost_amount is not None
                else parent.cost_amount
            ),
            "supplier_quantity": payload.supplier_quantity or Decimal("0.00"),
            "image_url": payload.image_url or parent.image_url,
        }
    )
    if payload.weight is not None:
        data["weight"] = payload.weight
    parent_id = parent.id
    variant = await crud_product.create(
        session=session, data=ProductCreate.model_validate(data), user=current_user
    )
    parent = await session.get(Product, parent_id)  # type: ignore[assignment]
    assert parent is not None
    await refresh_parent_from_variants(session, parent)
    await session.commit()
    await session.refresh(variant)
    return (await publish_with_availability(session, [variant]))[0]


@router.delete("/{product_id}/variants/{variant_id}", response_model=ProductPublic)
async def admin_deactivate_variant(
    session: SessionDep,
    current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    variant_id: uuid.UUID,
) -> ProductPublic:
    """Retire a variant (soft: past orders keep referencing it)."""
    parent = await _load_parent(session, product_id)
    variant = await session.get(Product, variant_id)
    if variant is None or variant.parent_product_id != parent.id:
        raise AppError(
            code="product.variant.not_found",
            status_code=404,
            message=f"Variant '{variant_id}' not found under product '{product_id}'",
            details={"product_id": str(product_id), "variant_id": str(variant_id)},
        )
    parent_id = parent.id
    updated = await crud_product.update(
        session=session,
        id=variant_id,
        data={"is_active": False},
        user=current_user,
        record=variant,
    )
    parent = await session.get(Product, parent_id)  # type: ignore[assignment]
    assert parent is not None
    await refresh_parent_from_variants(session, parent)
    await session.commit()
    # The commit expired the row; reload it before serialising (no lazy IO).
    await session.refresh(updated)
    return ProductPublic.model_validate(updated)
