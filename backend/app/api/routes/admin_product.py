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

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep, module_required
from app.core.config import settings
from app.core.content_i18n import (
    PRODUCT_FIELDS,
    InvalidTranslations,
    clean_translations,
)
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.integrations.models.supplier import Supplier
from app.features.integrations.services.supplier_attachment import (
    attach_now,
    detach,
)
from app.features.inventory.services.availability import publish_with_availability
from app.features.product.crud.product import crud_product
from app.features.product.models.brand import Brand
from app.features.product.models.price_group import PriceGroup
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
from app.features.product.models.product_group_price import ProductGroupPrice
from app.features.product.models.product_link import (
    ProductLink,
    ProductLinkPublic,
    ProductLinkWrite,
)
from app.features.product.services.group_pricing import apply_discount
from app.features.product.services.manual_specs import (
    SpecFormResponse,
    SpecValueWrite,
    apply_manual_specs,
    spec_form_rows,
)
from app.features.product.services.overrides import (
    clean_gallery_urls,
    merge_locks,
    release_lock,
)
from app.features.product.services.pricing import CurrencyRateMissing, PricingContext
from app.features.product.services.related import replace_product_links
from app.features.product.services.variants import (
    apply_price_extras,
    list_variants,
    option_axes,
    refresh_parent_from_variants,
    supplemented_price,
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


def _product_translations(
    data: dict[str, Any], *, previous: dict[str, Any] | None, source: dict[str, Any]
) -> dict[str, Any]:
    """Validated, stamped translations of the texts (R9 / T3)."""
    try:
        return clean_translations(
            data.get("translations"),
            previous=previous,
            source_values=source,
            fields=PRODUCT_FIELDS,
        )
    except InvalidTranslations as exc:
        raise AppError(
            code="product.translations.invalid",
            status_code=400,
            message=f"Traductions invalides : {exc}",
            details={"field": "translations"},
        ) from exc


@router.get("/manufacturers", response_model=list[str])
async def admin_list_manufacturers(
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> list[str]:
    """The brands the product form proposes: every manufacturer already on a
    product (one spelling per brand — the most frequent — so « HP » and
    « hp » stop coexisting) and the brands of the catalogue, sorted."""
    clean = func.nullif(func.trim(col(Product.manufacturer)), "")
    rows = (
        await session.exec(
            select(clean, func.count())
            .where(clean.is_not(None))
            .group_by(clean)
            .order_by(func.count().desc(), clean)
        )
    ).all()
    by_key: dict[str, str] = {}
    for name, _count in rows:
        key = str(name).casefold()
        by_key.setdefault(key, str(name))
    brands = (
        await session.exec(
            select(col(Brand.name)).where(col(Brand.is_active).is_(True))
        )
    ).all()
    for name in brands:
        text = str(name).strip()
        if text:
            by_key.setdefault(text.casefold(), text)
    return sorted(by_key.values(), key=str.casefold)


@router.get(
    "/specs-form",
    response_model=SpecFormResponse,
    dependencies=[Depends(module_required("specs"))],
)
async def admin_product_specs_form(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    product_id: uuid.UUID | None = None,
    category_id: uuid.UUID | None = None,
) -> SpecFormResponse:
    """The characteristics the product form offers to type (R9 / T4): one row
    per spec definition of the product's (or the chosen) category, with the
    current value and its source."""
    product = await _read_product(session, product_id) if product_id else None
    return await spec_form_rows(session, product=product, category_id=category_id)


@router.put(
    "/{product_id}/specs",
    response_model=SpecFormResponse,
    dependencies=[Depends(module_required("specs"))],
)
async def admin_set_product_specs(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    payload: list[SpecValueWrite],
) -> SpecFormResponse:
    """Write the typed characteristics as ``manual`` rows of ``product_specs``
    (the Icecat projection never rewrites them); a blank value removes the row."""
    product = await _read_product(session, product_id)
    try:
        await apply_manual_specs(session, product, payload)
    except KeyError as exc:
        raise AppError(
            code="product.spec.unknown",
            status_code=400,
            message=f"Caractéristique inconnue : {exc.args[0]}",
            details={"key": exc.args[0]},
        ) from exc
    except ValueError as exc:
        raise AppError(
            code="product.spec.invalid",
            status_code=400,
            message=str(exc),
            details={"field": "specs"},
        ) from exc
    await session.commit()
    await session.refresh(product)
    return await spec_form_rows(session, product=product, category_id=None)


@router.get("/{product_id}/links", response_model=list[ProductLinkPublic])
async def admin_list_product_links(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    product_id: uuid.UUID,
) -> list[ProductLinkPublic]:
    """Manual accessories and alternatives of a product (R9 / T7), in order."""
    product = await _read_product(session, product_id)
    return await _links_public(session, product)


@router.put("/{product_id}/links", response_model=list[ProductLinkPublic])
async def admin_set_product_links(
    session: SessionDep,
    _current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    payload: list[ProductLinkWrite],
) -> list[ProductLinkPublic]:
    """Replace the manual links of a product (R9 / T7)."""
    product = await _read_product(session, product_id)
    try:
        await replace_product_links(session, product, payload)
    except ValueError as exc:
        raise AppError(
            code="product.links.invalid",
            status_code=400,
            message=str(exc),
            details={"field": "links"},
        ) from exc
    await session.commit()
    await session.refresh(product)
    return await _links_public(session, product)


async def _links_public(
    session: SessionDep, product: Product
) -> list[ProductLinkPublic]:
    rows = (
        await session.exec(
            select(ProductLink, Product)
            .join(Product, col(Product.id) == col(ProductLink.linked_product_id))
            .where(ProductLink.product_id == product.id)
            .order_by(
                col(ProductLink.position).asc(),
                col(ProductLink.kind).asc(),
                col(ProductLink.created_at).asc(),
            )
        )
    ).all()
    return [
        ProductLinkPublic(
            id=link.id,
            linked_product_id=link.linked_product_id,
            kind=link.kind,
            position=link.position,
            name=target.name,
            vendor_part_number=target.vendor_part_number,
            supplier_sku=target.supplier_sku,
            image_url=target.image_url,
            is_active=bool(target.is_active and target.is_admin_active),
        )
        for link, target in rows
    ]


@router.post("", response_model=ProductPublic)
async def admin_create_product(
    session: SessionDep,
    current_user: CurrentSuperUser,
    payload: ProductCreate,
) -> ProductPublic:
    """Create a manually-managed product (never overwritten by the supplier sync)."""
    data = payload.model_dump(exclude_unset=True)
    if "gallery_urls" in data:
        data["gallery_urls"] = clean_gallery_urls(data["gallery_urls"])
    supplier = await _resolve_supplier(session, data.get("supplier_name"))
    _apply_supplier_defaults(data, supplier)
    if "translations" in data:
        data["translations"] = _product_translations(data, previous=None, source=data)
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
    #: Prices typed per group in the form (absent: the stored ones).
    group_prices: dict[uuid.UUID, Decimal] | None = None


class GroupPriceLine(BaseModel):
    """What one customer group pays for the article, and the margin left."""

    price_group_id: uuid.UUID
    label: str
    is_default: bool
    discount_pct: Decimal
    #: Price typed for the group on the article (None: the discount applies).
    typed_price: Decimal | None
    #: What the group pays: typed price, else reference − discount.
    price: Decimal | None
    margin_amount: Decimal | None
    margin_pct: Decimal | None


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
    #: One line per customer group (the reference price is the default's).
    groups: list[GroupPriceLine] = Field(default_factory=list)


async def _active_groups(session: SessionDep) -> list[PriceGroup]:
    rows = await session.exec(
        select(PriceGroup)
        .where(col(PriceGroup.is_active).is_(True))
        .order_by(col(PriceGroup.default).desc(), col(PriceGroup.label).asc())
    )
    return list(rows.all())


async def _stored_group_prices(
    session: SessionDep, product_id: uuid.UUID
) -> dict[uuid.UUID, Decimal]:
    rows = await session.exec(
        select(ProductGroupPrice).where(col(ProductGroupPrice.product_id) == product_id)
    )
    return {row.price_group_id: Decimal(row.price) for row in rows.all()}


def _group_lines(
    groups: list[PriceGroup],
    typed: dict[uuid.UUID, Decimal],
    *,
    reference: Decimal | None,
    context: PricingContext,
    product: Product,
) -> list[GroupPriceLine]:
    lines = []
    for group in groups:
        typed_price = typed.get(group.id)
        if typed_price is not None:
            price: Decimal | None = typed_price
        elif reference is not None:
            price = apply_discount(reference, group.discount_pct)
        else:
            price = None
        figures = context.margin(product, price) if price is not None else None
        lines.append(
            GroupPriceLine(
                price_group_id=group.id,
                label=group.label,
                is_default=group.default,
                discount_pct=Decimal(group.discount_pct or 0),
                typed_price=typed_price,
                price=price,
                margin_amount=figures.margin_amount if figures else None,
                margin_pct=figures.margin_pct if figures else None,
            )
        )
    return lines


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
    groups = await _active_groups(session)
    typed = (
        {gid: price for gid, price in payload.group_prices.items() if price is not None}
        if payload.group_prices is not None
        else (
            await _stored_group_prices(session, payload.product_id)
            if payload.product_id is not None
            else {}
        )
    )
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
        return empty.model_copy(
            update={
                "note": f"Pas de taux de change pour {exc}",
                "groups": _group_lines(
                    groups, typed, reference=None, context=context, product=draft
                ),
            }
        )
    lines = _group_lines(groups, typed, reference=price, context=context, product=draft)
    figures = context.margin(draft, price)
    if figures is None:
        return empty.model_copy(
            update={
                "price_incl_tax": price,
                "note": "Saisissez le coût d'achat pour voir la marge.",
                "groups": lines,
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
        groups=lines,
    )


class GroupPriceInput(BaseModel):
    price_group_id: uuid.UUID
    #: Tax-inclusive price for the group; None removes it (discount applies).
    #: 0 is refused: it would sell the article for free to that group.
    price: Decimal | None = Field(default=None, gt=0, max_digits=14, decimal_places=2)


class GroupPricesUpdate(BaseModel):
    prices: list[GroupPriceInput]


class GroupPriceStored(BaseModel):
    price_group_id: uuid.UUID
    price: Decimal


@router.get("/{product_id}/group-prices", response_model=list[GroupPriceStored])
async def get_group_prices(
    product_id: uuid.UUID,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> list[GroupPriceStored]:
    """Prices typed per customer group on the article."""
    stored = await _stored_group_prices(session, product_id)
    return [GroupPriceStored(price_group_id=k, price=v) for k, v in stored.items()]


@router.put("/{product_id}/group-prices", response_model=list[GroupPriceStored])
async def set_group_prices(
    product_id: uuid.UUID,
    payload: GroupPricesUpdate,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> list[GroupPriceStored]:
    """Set (or clear, with a null price) the article's price per group."""
    if await session.get(Product, product_id) is None:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message="Product not found",
            details={"product_id": str(product_id)},
        )
    group_ids = {g.id for g in await _active_groups(session)}
    seen: set[uuid.UUID] = set()
    for entry in payload.prices:
        if entry.price_group_id in seen:
            raise AppError(
                code="price_group.duplicate",
                status_code=400,
                message="Un groupe apparaît deux fois dans la grille",
                details={"price_group_id": str(entry.price_group_id)},
            )
        seen.add(entry.price_group_id)
    existing = {
        row.price_group_id: row
        for row in (
            await session.exec(
                select(ProductGroupPrice).where(
                    col(ProductGroupPrice.product_id) == product_id
                )
            )
        ).all()
    }
    for entry in payload.prices:
        if entry.price_group_id not in group_ids:
            raise AppError(
                code="price_group.not_found",
                status_code=404,
                message="Groupe tarifaire introuvable",
                details={"price_group_id": str(entry.price_group_id)},
            )
        row = existing.get(entry.price_group_id)
        if entry.price is None:
            if row is not None:
                await session.delete(row)
            continue
        if row is None:
            row = ProductGroupPrice(
                product_id=product_id,
                price_group_id=entry.price_group_id,
                price=entry.price,
            )
        row.price = entry.price
        session.add(row)
    await session.commit()
    stored = await _stored_group_prices(session, product_id)
    return [GroupPriceStored(price_group_id=k, price=v) for k, v in stored.items()]


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
    if "gallery_urls" in changed:
        try:
            changed["gallery_urls"] = clean_gallery_urls(changed["gallery_urls"])
        except ValueError as exc:
            raise AppError(
                code="product.gallery.invalid",
                status_code=400,
                message=f"Galerie invalide : {exc}",
                details={"field": "gallery_urls"},
            ) from exc
    if "translations" in changed:
        source = {f: changed.get(f, getattr(product, f, None)) for f in PRODUCT_FIELDS}
        changed["translations"] = _product_translations(
            changed, previous=product.translations, source=source
        )
    if "supplier_name" in changed and changed["supplier_name"] != product.supplier_name:
        supplier = await _resolve_supplier(session, changed["supplier_name"])
        # Re-linking a manual product to another supplier moves its origin
        # and customs regime along, unless the same payload sets them.
        if not product.is_supplier_managed:
            _apply_supplier_defaults(changed, supplier)
    merged = merge_locks(product.overridden_fields, changed)

    if product.parent_product_id is not None and (
        "price_extra" in changed or "base_price" in changed
    ):
        # A variant with a supplement (R9 / T6) has a derived price.
        extra = changed.get("price_extra", product.price_extra)
        if extra is not None:
            parent = await session.get(Product, product.parent_product_id)
            if parent is not None:
                changed["base_price"] = supplemented_price(parent, extra)

    update_data: dict[str, Any] = {**changed, "overridden_fields": merged}
    updated = await crud_product.update(
        session=session,
        id=product_id,
        data=update_data,
        user=current_user,
        record=product,
    )
    if updated.has_variants and "base_price" in changed:
        # The parent's price moved: the supplements follow (R9 / T6).
        await apply_price_extras(session, updated)
        await session.commit()
        await session.refresh(updated)
    await _refresh_parent_of(session, updated)
    return ProductPublic.model_validate(updated)


class SupplierAttachRequest(BaseModel):
    """Supplier and reference to attach; both default to the product's own."""

    supplier_name: str | None = Field(default=None, max_length=100)
    supplier_sku: str | None = Field(default=None, max_length=100)


class SupplierAttachResponse(BaseModel):
    #: ``adopted`` (cost and stock taken now) or ``pending`` (next file import).
    status: str
    message: str
    product: ProductPublic


async def _read_product(session: SessionDep, product_id: uuid.UUID) -> Product:
    try:
        return await crud_product.read(session=session, id=product_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="product.not_found",
            status_code=404,
            message=f"Product '{product_id}' not found",
            details={"product_id": str(product_id)},
        ) from exc


@router.post("/{product_id}/attach-supplier", response_model=SupplierAttachResponse)
async def admin_attach_supplier(
    session: SessionDep,
    current_user: CurrentSuperUser,
    product_id: uuid.UUID,
    payload: SupplierAttachRequest,
) -> SupplierAttachResponse:
    """Attach a product to a supplier reference now (« Rattacher maintenant »).

    API supplier: the reference is fetched and the product adopted on the
    spot (cost, stock, mapping; the admin's content stays locked). File
    supplier: the link is recorded, the next import adopts it.
    """
    actor_id = current_user.id
    product = await _read_product(session, product_id)
    code = payload.supplier_name or product.supplier_name
    sku = payload.supplier_sku or product.supplier_sku or ""
    supplier = await _resolve_supplier(session, code)
    if supplier is None:
        raise AppError(
            code="supplier.attach.missing_reference",
            status_code=400,
            message="Choisissez le fournisseur et saisissez sa référence (SKU)",
            details={"product_id": str(product_id)},
        )
    outcome = await attach_now(session, product, supplier, supplier_sku=sku)
    status, message = outcome.status, outcome.message
    await session.commit()
    refreshed = await crud_product.read(session=session, id=product_id)
    await _refresh_parent_of(session, refreshed)
    logger.info("Admin %s attached product %s (%s)", actor_id, product_id, status)
    return SupplierAttachResponse(
        status=status, message=message, product=ProductPublic.model_validate(refreshed)
    )


@router.post("/{product_id}/detach-supplier", response_model=ProductPublic)
async def admin_detach_supplier(
    session: SessionDep,
    current_user: CurrentSuperUser,
    product_id: uuid.UUID,
) -> ProductPublic:
    """Turn a supplier product back into a manual one (« Détacher »)."""
    actor_id = current_user.id
    product = await _read_product(session, product_id)
    await detach(session, product)
    await session.commit()
    refreshed = await crud_product.read(session=session, id=product_id)
    await _refresh_parent_of(session, refreshed)
    logger.info("Admin %s detached product %s from its supplier", actor_id, product_id)
    return ProductPublic.model_validate(refreshed)


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
    # The commit expired the variant: reload it for the response.
    await session.refresh(product)


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
    #: Supplement over the parent's price (R9 / T6): the price is then derived.
    price_extra: Decimal | None = None
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
                supplemented_price(parent, payload.price_extra)
                if payload.price_extra is not None
                else payload.base_price
                if payload.base_price is not None
                else parent.base_price
            ),
            "price_extra": payload.price_extra,
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
