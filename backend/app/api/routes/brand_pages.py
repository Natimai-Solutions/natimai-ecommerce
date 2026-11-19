"""Brand sheets: the storefront brand page and the admin « Marques » screen
(chantier accueil et messagerie, lot BR).

Products are linked to a sheet from the supplier's manufacturer name
(``features/product/services/brands``). The storefront only shows validated
sheets; the admin checks the ones created on the fly, renames them, gives
them a logo and aliases, or merges a spelling into the right sheet.
"""

from __future__ import annotations

import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, or_
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.api.routes.media import request_origin
from app.core.content_i18n import (
    BRAND_FIELDS,
    InvalidTranslations,
    clean_translations,
    translated_values,
)
from app.core.errors import AppError
from app.core.i18n import request_locale
from app.features.media.models import MediaAsset
from app.features.media.service import public_base_url, to_public
from app.features.product.models.brand import Brand, BrandAlias
from app.features.product.models.product import Product
from app.features.product.services import brands as brand_service

router = APIRouter(prefix="/brands", tags=["brand"])
admin_router = APIRouter(prefix="/admin/brands", tags=["admin-brand"])


class BrandLogo(BaseModel):
    src: str
    srcset: str | None = None
    width: int | None = None
    height: int | None = None


class BrandPagePublic(BaseModel):
    """What the storefront shows of a brand."""

    id: uuid.UUID
    name: str
    slug: str
    description: str | None = None
    logo: BrandLogo | None = None
    product_count: int = 0


class AdminBrand(BrandPagePublic):
    is_validated: bool
    #: The description in the other offered languages.
    translations: dict[str, dict[str, Any]] = {}
    is_active: bool
    aliases: list[str] = []
    media_id: uuid.UUID | None = None


class AdminBrandList(BaseModel):
    data: list[AdminBrand]
    count: int
    to_validate: int


class BrandWrite(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    slug: str | None = Field(default=None, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    media_id: uuid.UUID | None = None
    is_validated: bool = True
    is_active: bool = True
    aliases: list[str] = Field(default_factory=list, max_length=50)
    translations: dict[str, dict[str, Any]] = Field(default_factory=dict)


class BrandMerge(BaseModel):
    target_id: uuid.UUID


class LinkResult(BaseModel):
    linked: int


def _description(brand: Brand) -> str | None:
    """The description in the visitor's language (the source otherwise)."""
    texts = translated_values(brand.translations, BRAND_FIELDS, request_locale())
    return texts.get("description") or brand.description


def _not_found() -> AppError:
    return AppError(code="brand.not_found", status_code=404, message="Brand not found.")


async def brand_logo(
    session: SessionDep, brand: Brand, base_url: str
) -> BrandLogo | None:
    if brand.media_id:
        media = await session.get(MediaAsset, brand.media_id)
        if media is not None and media.is_active:
            described = to_public(media, base_url)
            return BrandLogo(
                src=described.url,
                srcset=described.srcset,
                width=described.width,
                height=described.height,
            )
    if brand.image_url:
        return BrandLogo(src=brand.image_url)
    return None


async def _product_counts(
    session: SessionDep, brand_ids: list[uuid.UUID]
) -> dict[uuid.UUID, int]:
    if not brand_ids:
        return {}
    rows = (
        await session.exec(
            select(col(Product.brand_id), func.count())
            .where(
                col(Product.brand_id).in_(brand_ids),
                col(Product.is_active).is_(True),
                # A variant counts with its product, as the catalogue lists it.
                col(Product.parent_product_id).is_(None),
            )
            .group_by(col(Product.brand_id))
        )
    ).all()
    return {row[0]: int(row[1]) for row in rows if row[0] is not None}


# --------------------------------------------------------------- storefront


@router.get("/page/{slug}", response_model=BrandPagePublic, summary="Brand page")
async def get_brand_page(
    slug: str, request: Request, session: SessionDep
) -> BrandPagePublic:
    """A validated, active brand by its path (``/marque/<slug>``)."""
    brand = (
        await session.exec(select(Brand).where(col(Brand.slug) == slug.lower()))
    ).first()
    if brand is None or not brand.is_validated or not brand.is_active:
        raise _not_found()
    counts = await _product_counts(session, [brand.id])
    return BrandPagePublic(
        id=brand.id,
        name=brand.name,
        slug=brand.slug or slug,
        description=_description(brand),
        logo=await brand_logo(session, brand, public_base_url(request_origin(request))),
        product_count=counts.get(brand.id, 0),
    )


async def showcase(
    session: SessionDep, base_url: str, limit: int
) -> list[tuple[Brand, BrandLogo, int]]:
    """The validated brands that have a logo and products on sale, the
    best-stocked first (the brand page list and the homepage brand strip)."""
    brands = (
        await session.exec(
            select(Brand).where(
                col(Brand.is_validated).is_(True),
                col(Brand.is_active).is_(True),
                col(Brand.slug).is_not(None),
                or_(
                    col(Brand.media_id).is_not(None),
                    col(Brand.image_url).is_not(None),
                ),
            )
        )
    ).all()
    counts = await _product_counts(session, [b.id for b in brands])
    shown: list[tuple[Brand, BrandLogo, int]] = []
    for brand in sorted(brands, key=lambda b: (-counts.get(b.id, 0), b.name.lower())):
        if not counts.get(brand.id):
            continue
        logo = await brand_logo(session, brand, base_url)
        if logo is None:
            continue
        shown.append((brand, logo, counts[brand.id]))
        if len(shown) >= limit:
            break
    return shown


@router.get(
    "/showcase", response_model=list[BrandPagePublic], summary="Brands with a logo"
)
async def brand_showcase(
    request: Request,
    session: SessionDep,
    limit: Annotated[int, Query(ge=1, le=48)] = 24,
) -> list[BrandPagePublic]:
    """The validated brands that have a logo and products on sale, the
    best-stocked first."""
    return [
        BrandPagePublic(
            id=brand.id,
            name=brand.name,
            slug=brand.slug or "",
            description=_description(brand),
            logo=logo,
            product_count=count,
        )
        for brand, logo, count in await showcase(
            session, public_base_url(request_origin(request)), limit
        )
    ]


class BrandSitemapEntry(BaseModel):
    slug: str
    modify_at: str | None = None


@router.get("/sitemap", response_model=list[BrandSitemapEntry], summary="Brand pages")
async def brand_sitemap(session: SessionDep) -> list[BrandSitemapEntry]:
    """The brand pages search engines should know: validated, active, with
    products on sale (the storefront's sitemap.xml lists them)."""
    brands = (
        await session.exec(
            select(Brand).where(
                col(Brand.is_validated).is_(True),
                col(Brand.is_active).is_(True),
                col(Brand.slug).is_not(None),
            )
        )
    ).all()
    counts = await _product_counts(session, [b.id for b in brands])
    return [
        BrandSitemapEntry(
            slug=b.slug or "",
            modify_at=b.modify_at.isoformat() if b.modify_at else None,
        )
        for b in sorted(brands, key=lambda b: b.slug or "")
        if counts.get(b.id)
    ]


# -------------------------------------------------------------------- admin


async def _admin_view(
    session: SessionDep, brands: list[Brand], base_url: str
) -> list[AdminBrand]:
    ids = [b.id for b in brands]
    counts = await _product_counts(session, ids)
    aliases: dict[uuid.UUID, list[str]] = {}
    if ids:
        for row in (
            await session.exec(
                select(BrandAlias)
                .where(col(BrandAlias.brand_id).in_(ids))
                .order_by(col(BrandAlias.alias))
            )
        ).all():
            aliases.setdefault(row.brand_id, []).append(row.alias)
    return [
        AdminBrand(
            id=b.id,
            name=b.name,
            slug=b.slug or "",
            description=b.description,
            logo=await brand_logo(session, b, base_url),
            product_count=counts.get(b.id, 0),
            is_validated=b.is_validated,
            is_active=b.is_active,
            aliases=aliases.get(b.id, []),
            media_id=b.media_id,
            translations=b.translations or {},
        )
        for b in brands
    ]


@admin_router.get("", response_model=AdminBrandList, summary="Brand sheets")
async def admin_list_brands(
    request: Request,
    session: SessionDep,
    _admin: CurrentSuperUser,
    q: Annotated[str | None, Query(max_length=100)] = None,
    to_validate: Annotated[bool, Query()] = False,
) -> AdminBrandList:
    """Every sheet, those to validate first, then by name."""
    query = select(Brand)
    if to_validate:
        query = query.where(col(Brand.is_validated).is_(False))
    if q and q.strip():
        pattern = f"%{q.strip()}%"
        query = query.where(
            or_(
                col(Brand.name).ilike(pattern),
                col(Brand.id).in_(
                    select(col(BrandAlias.brand_id)).where(
                        col(BrandAlias.alias).ilike(pattern)
                    )
                ),
            )
        )
    brands = list(
        (
            await session.exec(
                query.order_by(col(Brand.is_validated), func.lower(col(Brand.name)))
            )
        ).all()
    )
    pending = (
        await session.exec(
            select(func.count())
            .select_from(Brand)
            .where(col(Brand.is_validated).is_(False))
        )
    ).one()
    return AdminBrandList(
        data=await _admin_view(
            session, brands, public_base_url(request_origin(request))
        ),
        count=len(brands),
        to_validate=int(pending),
    )


async def _check(
    session: SessionDep, body: BrandWrite, brand_id: uuid.UUID | None
) -> str:
    slug = brand_service.slugify(body.slug or body.name)
    taken = (
        await session.exec(
            select(Brand.id).where(col(Brand.slug) == slug, col(Brand.id) != brand_id)
        )
    ).first()
    if taken is not None:
        raise AppError(
            code="brand.slug_taken",
            status_code=409,
            message="Another brand already uses the address {slug}.",
            details={"slug": slug, "field": "slug"},
        )
    if body.media_id is not None:
        media = await session.get(MediaAsset, body.media_id)
        if media is None or not media.is_active:
            raise AppError(
                code="brand.media_not_found",
                status_code=422,
                message="Image not found.",
                details={"field": "media_id"},
            )
    return slug


async def _save(
    session: SessionDep, brand: Brand, body: BrandWrite, slug: str, base_url: str
) -> AdminBrand:
    old_name = brand.name
    brand.name = body.name.strip()
    brand.slug = slug
    brand.description = (body.description or "").strip() or None
    try:
        brand.translations = clean_translations(
            body.translations,
            previous=brand.translations,
            source_values={"description": brand.description},
            fields=BRAND_FIELDS,
        )
    except InvalidTranslations as exc:
        raise AppError(
            code="brand.translations",
            status_code=400,
            message="Invalid translations.",
            details={"field": "translations", "problem": str(exc)},
        ) from exc
    brand.media_id = body.media_id
    brand.is_validated = body.is_validated
    brand.is_active = body.is_active
    session.add(brand)
    await session.flush()
    await brand_service.set_aliases(session, brand, body.aliases)
    # Renamed: the former name stays an alias (the products the suppliers
    # still name so would go back to a new sheet « to validate »).
    await brand_service.keep_old_name(session, brand, old_name)
    brand_id = brand.id
    await session.commit()
    saved = await session.get(Brand, brand_id)
    assert saved is not None
    return (await _admin_view(session, [saved], base_url))[0]


@admin_router.post("", response_model=AdminBrand, status_code=201)
async def admin_create_brand(
    body: BrandWrite, request: Request, session: SessionDep, _admin: CurrentSuperUser
) -> AdminBrand:
    slug = await _check(session, body, None)
    if await brand_service.find_brand(session, body.name) is not None:
        raise AppError(
            code="brand.exists",
            status_code=409,
            message="A brand with this name already exists.",
            details={"field": "name"},
        )
    return await _save(
        session,
        Brand(name=body.name),
        body,
        slug,
        public_base_url(request_origin(request)),
    )


@admin_router.put("/{brand_id}", response_model=AdminBrand)
async def admin_update_brand(
    brand_id: uuid.UUID,
    body: BrandWrite,
    request: Request,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> AdminBrand:
    brand = await session.get(Brand, brand_id)
    if brand is None:
        raise _not_found()
    # Only a rename is checked: a sheet saved under its own name (or one of
    # its aliases) must stay editable, even beside a hidden namesake.
    renamed = brand_service.brand_key(body.name) != brand_service.brand_key(brand.name)
    same = await brand_service.find_brand(session, body.name) if renamed else None
    if same is not None and same.id != brand_id:
        raise AppError(
            code="brand.exists",
            status_code=409,
            message="A brand with this name already exists.",
            details={"field": "name"},
        )
    slug = await _check(session, body, brand_id)
    return await _save(
        session, brand, body, slug, public_base_url(request_origin(request))
    )


@admin_router.post("/{brand_id}/merge", response_model=AdminBrand)
async def admin_merge_brand(
    brand_id: uuid.UUID,
    body: BrandMerge,
    request: Request,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> AdminBrand:
    """This sheet is a spelling of another: its products and aliases move to
    the target, its name becomes an alias of it, and it goes."""
    source = await session.get(Brand, brand_id)
    target = await session.get(Brand, body.target_id)
    if source is None or target is None:
        raise _not_found()
    if source.id == target.id:
        raise AppError(
            code="brand.merge_self",
            status_code=400,
            message="A brand cannot be merged into itself.",
        )
    target_id = target.id
    await brand_service.merge_brands(session, source, target)
    await session.commit()
    merged = await session.get(Brand, target_id)
    assert merged is not None
    return (
        await _admin_view(session, [merged], public_base_url(request_origin(request)))
    )[0]


@admin_router.delete("/{brand_id}", status_code=204)
async def admin_delete_brand(
    brand_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> None:
    """Delete a sheet: its products lose the link until the next pass links
    them again (to a new sheet to validate, or to an alias)."""
    brand = await session.get(Brand, brand_id)
    if brand is None:
        raise _not_found()
    selections = await brand_service.homepage_selections_of(session, brand_id)
    if selections:
        # The homepage selection would empty itself without a word: merge
        # the sheet into another one, or change the selection first.
        raise AppError(
            code="brand.in_use",
            status_code=409,
            message="This brand is used by a homepage selection: {titles}.",
            details={"titles": ", ".join(b.title or "—" for b in selections)},
        )
    await session.delete(brand)
    await session.commit()


@admin_router.post("/link", response_model=LinkResult)
async def admin_link_products(
    session: SessionDep, _admin: CurrentSuperUser
) -> LinkResult:
    """Link now the products without a sheet (the worker does it hourly)."""
    return LinkResult(linked=await brand_service.link_unbranded_products(session))
