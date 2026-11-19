"""Storefront homepage: its sections, in order, edited from the admin.

``GET /homepage`` is public: the sections a visitor sees (published, within
their dates, for every visitor), with the products of the product sections
priced for a visitor. It reads no identity, so a signed-in customer's token
changes nothing in it. ``GET /homepage/personal`` is the page of the signed-in
customer: the sections of their audience, the products at their prices
(chantier accueil et messagerie, R1 and R8). The admin routes list, create,
replace, reorder and delete sections.
"""

from __future__ import annotations

import datetime
import hmac
import uuid
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Header, Query, Request, Response
from jwt import InvalidTokenError
from pydantic import BaseModel
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, CurrentUser, SessionDep
from app.api.routes.brand_pages import brand_logo, showcase
from app.api.routes.media import request_origin
from app.core.config import settings
from app.core.content_i18n import (
    CATEGORY_FIELDS,
    HOMEPAGE_BLOCK_FIELDS,
    InvalidTranslations,
    clean_translations,
    localize_all,
)
from app.core.datetimes import as_utc, utcnow
from app.core.errors import AppError
from app.core.i18n import default_locale, request_locale
from app.core.security import create_preview_token, decode_token
from app.features.content.homepage_collections import (
    chosen_categories,
    collection_products,
    section_items,
)
from app.features.content.homepage_personal import (
    current_order,
    reorder_products,
    wishlist_products,
)
from app.features.content.homepage_sections import (
    ACCOUNT_SOURCES,
    InvalidSection,
    Viewer,
    audiences_overlap,
    clean_audience,
    clean_config,
    is_safe_link,
    is_shown_to,
    stored_config,
)
from app.features.content.models import (
    HOMEPAGE_BLOCK_KINDS,
    HOMEPAGE_SEO_FIELDS,
    HOMEPAGE_TITLE_OPTIONAL_KINDS,
    HomepageBlock,
    HomepageBlockItem,
    HomepageBlockPublic,
    HomepageBlockWrite,
    HomepageBrandTile,
    HomepageCategoryTile,
    HomepageImage,
    HomepageItemPublic,
    HomepageItemWrite,
    HomepageOrder,
    HomepageReassurance,
    HomepageSeo,
    HomepageSeoPublic,
    HomepageSeoWrite,
)
from app.features.inventory.services.availability import publish_with_availability
from app.features.media.models import MediaAsset
from app.features.media.service import public_base_url, to_public
from app.features.product.crud.product import crud_product
from app.features.product.models.brand import Brand
from app.features.product.models.category import Category
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import Product, ProductPublic
from app.features.product.services.group_pricing import resolve_customer_group
from app.features.product.services.popularity import popular_products
from app.features.user.models.user import User

router = APIRouter(tags=["homepage"])


class HomepageSectionPublic(HomepageBlockPublic):
    """A section of the storefront homepage, with its products when it shows
    some (featured, most viewed)."""

    products: list[ProductPublic] | None = None


class HomepagePublic(BaseModel):
    """The storefront homepage: its sections in display order (the hero, if
    any, first), and its title and description for search engines."""

    sections: list[HomepageSectionPublic] = []
    seo: HomepageSeoPublic | None = None
    #: Preview only: the announcement of the simulated date (lot A4).
    announcement: HomepageSectionPublic | None = None


class PreviewLink(BaseModel):
    """What the admin opens: the storefront address and a 15-minute token,
    passed in the address fragment (never sent to the server)."""

    token: str
    expires_at: datetime.datetime
    storefront_url: str


def _invalid(message: str, code: str, field: str) -> AppError:
    return AppError(
        code=code, status_code=400, message=message, details={"field": field}
    )


def _validate(body: HomepageBlockWrite) -> None:
    if body.kind not in HOMEPAGE_BLOCK_KINDS:
        raise AppError(
            code="homepage.kind",
            status_code=400,
            message="Unknown section type: {kind}.",
            details={"field": "kind", "kind": body.kind},
        )
    if body.kind not in HOMEPAGE_TITLE_OPTIONAL_KINDS and not body.title.strip():
        raise _invalid("A title is required.", "homepage.title", "title")
    if body.kind == "rich_text" and not (body.body_html or "").strip():
        raise _invalid("The text is required.", "homepage.body", "body_html")
    if body.kind != "rich_text":
        body.body_html = None
    link = (body.cta_link or "").strip()
    # A storefront path or an https URL: never javascript: or a protocol-relative
    # URL that would take the visitor elsewhere unnoticed.
    if link and not is_safe_link(link):
        raise _invalid(
            "Link: a path of the site (/catalogue…) or an https:// address.",
            "homepage.link",
            "cta_link",
        )
    image = (body.image_url or "").strip()
    if image and not image.startswith("https://") and not image.startswith("http://"):
        raise _invalid(
            "Image: a complete http(s) address.", "homepage.image", "image_url"
        )
    if (
        body.starts_at
        and body.ends_at
        and as_utc(body.ends_at) <= as_utc(body.starts_at)
    ):
        raise _invalid("The end must follow the start.", "homepage.dates", "ends_at")


async def _clean_sections_fields(
    session: SessionDep, body: HomepageBlockWrite
) -> tuple[dict[str, Any], dict[str, Any]]:
    """The section's settings and audience, checked (R1 / R8)."""
    try:
        config = clean_config(body.kind, body.config)
    except InvalidSection:
        raise _invalid("Invalid section settings.", "homepage.config", "config")
    try:
        audience = clean_audience(body.audience)
    except InvalidSection:
        raise _invalid("Invalid audience.", "homepage.audience", "audience")
    # The announcement is above the header of every page, rendered with the
    # page for everyone: a language may narrow it, an audience may not.
    if body.kind == "announcement" and audience["scope"] != "all":
        raise _invalid("Invalid audience.", "homepage.audience", "audience")
    for group_id in audience["price_group_ids"]:
        group = await session.get(PriceGroup, uuid.UUID(group_id))
        if group is None:
            raise _invalid("Invalid audience.", "homepage.audience", "audience")
    return config, audience


def _with_translations(
    body: HomepageBlockWrite, *, previous: dict[str, Any] | None
) -> dict[str, Any]:
    """The payload with its translations validated and stamped (R9 / T3)."""
    data = body.model_dump()
    try:
        data["translations"] = clean_translations(
            body.translations,
            previous=previous,
            source_values=data,
            fields=HOMEPAGE_BLOCK_FIELDS,
        )
    except InvalidTranslations as exc:
        raise AppError(
            code="homepage.translations",
            status_code=400,
            message="Invalid translations.",
            details={"field": "translations", "problem": str(exc)},
        ) from exc
    return data


async def _to_public(
    session: SessionDep, block: HomepageBlock, base_url: str, *, localized: bool = False
) -> HomepageSectionPublic:
    item = HomepageSectionPublic.model_validate(block, from_attributes=True)
    if localized:
        # Storefront: texts in the visitor's language (R9 / T3).
        localize_all([item], HOMEPAGE_BLOCK_FIELDS)
    alt = item.alt or ""
    if block.media_id:
        media = await session.get(MediaAsset, block.media_id)
        if media is not None and media.is_active:
            described = to_public(media, base_url)
            item.image = HomepageImage(
                src=described.url,
                srcset=described.srcset,
                width=described.width,
                height=described.height,
                alt=alt or (media.alt or ""),
            )
    if item.image is None and block.image_url:
        item.image = HomepageImage(src=block.image_url, alt=alt)
    if block.kind == "categories" and (block.config or {}).get("mode") == "manual":
        chosen = await chosen_categories(session, block.id)
        if localized:
            localize_all([c for c, _ in chosen], CATEGORY_FIELDS)
        item.categories = [
            HomepageCategoryTile(
                id=category.id,
                title=listed.label
                or (category.display_name or "").strip()
                or category.name,
                image_url=category.image_url,
            )
            for category, listed in chosen
        ]
    if block.kind == "reassurance":
        item.reassurance = _reassurance(block, localized=localized)
    if block.kind == "brand_strip" and localized:
        item.brands = await _brand_tiles(session, block, base_url)
    if not localized:
        names: list[HomepageItemPublic] = []
        for listed in await section_items(session, block.id):
            target: Product | Category | Brand | None
            if listed.product_id:
                target = await session.get(Product, listed.product_id)
            elif listed.category_id:
                target = await session.get(Category, listed.category_id)
            else:
                target = await session.get(Brand, listed.brand_id)
            names.append(
                HomepageItemPublic(
                    product_id=listed.product_id,
                    category_id=listed.category_id,
                    brand_id=listed.brand_id,
                    label=listed.label,
                    name=getattr(target, "name", "") if target else "",
                )
            )
        item.items = names
    return item


def _reassurance(block: HomepageBlock, *, localized: bool) -> list[HomepageReassurance]:
    """The pictograms of a reassurance band, their text in the visitor's
    language (lot A3 / R5)."""
    locale = request_locale() if localized else default_locale()
    shown: list[HomepageReassurance] = []
    config = stored_config(block.kind, block.config)
    for raw in config["items"] if config else []:
        text = raw["text"]
        if localized and locale != default_locale():
            text = (raw.get("translations") or {}).get(locale) or text
        shown.append(
            HomepageReassurance(icon=raw["icon"], text=text, link=raw.get("link"))
        )
    return shown


async def _brand_tiles(
    session: SessionDep, block: HomepageBlock, base_url: str
) -> list[HomepageBrandTile]:
    """The brands of a brand strip: chosen, or the best-stocked with a logo.
    A brand without a logo, hidden or still to validate is left out."""
    config = stored_config(block.kind, block.config)
    tiles: list[HomepageBrandTile] = []
    if config is None:
        return tiles
    if config["mode"] == "manual":
        for listed in await section_items(session, block.id):
            brand = (
                await session.get(Brand, listed.brand_id) if listed.brand_id else None
            )
            if brand is None or not (brand.is_validated and brand.is_active):
                continue
            logo = await brand_logo(session, brand, base_url)
            if logo is None or not brand.slug:
                continue
            tiles.append(
                HomepageBrandTile(
                    id=brand.id,
                    name=brand.name,
                    slug=brand.slug,
                    logo=logo.src,
                    logo_srcset=logo.srcset,
                )
            )
        return tiles[: config["limit"]]
    for brand, logo, _count in await showcase(session, base_url, config["limit"]):
        tiles.append(
            HomepageBrandTile(
                id=brand.id,
                name=brand.name,
                slug=brand.slug or "",
                logo=logo.src,
                logo_srcset=logo.srcset,
            )
        )
    return tiles


def _is_live(block: HomepageBlock, now: datetime.datetime) -> bool:
    return (block.starts_at is None or as_utc(block.starts_at) <= now) and (
        block.ends_at is None or as_utc(block.ends_at) > now
    )


async def _section_products(
    session: SessionDep, block: HomepageBlock, *, customer: Any
) -> list[ProductPublic] | None:
    """The products of a product section, priced for ``customer`` (a user,
    or None for a visitor: the default group's prices)."""
    config = stored_config(block.kind, block.config)
    if config is None:
        return None
    if block.kind == "personal":
        if customer is None or config["source"] not in ("reorder", "wishlist"):
            return None
        finder = (
            reorder_products if config["source"] == "reorder" else wishlist_products
        )
        products = await finder(session, customer.id, config["limit"])
        return await publish_with_availability(session, products, customer=customer)
    if block.kind == "featured":
        products = await crud_product.get_featured(
            session=session, limit=config["limit"]
        )
    elif block.kind == "collection":
        products = await collection_products(session, block.id, config)
    elif block.kind == "popular":
        products = await popular_products(
            session,
            conditions=crud_product.storefront_conditions(),
            days=config["days"],
            limit=config["limit"],
        )
        await crud_product._apply_runtime_sale_prices(session, products)  # noqa: SLF001
    else:
        return None
    return await publish_with_availability(session, products, customer=customer)


async def _seo(session: SessionDep, *, localized: bool) -> HomepageSeoPublic | None:
    row = (await session.exec(select(HomepageSeo))).first()
    if row is None:
        return None
    seo = HomepageSeoPublic.model_validate(row, from_attributes=True)
    if localized:
        localize_all([seo], HOMEPAGE_SEO_FIELDS)
        seo.translations = {}
    return seo


async def _page(
    request: Request,
    session: SessionDep,
    *,
    viewer: Viewer,
    customer: Any,
    now: datetime.datetime | None = None,
    drafts: bool = False,
) -> HomepagePublic:
    """The sections ``viewer`` sees, in order: the first hero, then the rest.
    Two sections showing the same products (featured, then most viewed) do
    not show a product twice. ``now`` and ``drafts`` are the preview's (a
    simulated date, the unpublished sections too)."""
    now = now or utcnow()
    conditions = [col(HomepageBlock.is_active).is_(True)]
    if not drafts:
        conditions.append(col(HomepageBlock.is_published).is_(True))
    rows = (
        await session.exec(
            select(HomepageBlock)
            .where(*conditions)
            .order_by(col(HomepageBlock.position).asc(), col(HomepageBlock.title).asc())
        )
    ).all()
    visible = [
        b
        for b in rows
        if b.kind != "announcement"
        and _is_live(b, now)
        and is_shown_to(b.audience, viewer)
        # A customer's own section: never on a visitor's page (lot A5).
        and not (
            b.kind == "personal"
            and not viewer.signed_in
            and (b.config or {}).get("source") in ACCOUNT_SOURCES
        )
    ]
    hero = next((b for b in visible if b.kind == "hero"), None)
    ordered = ([hero] if hero else []) + [b for b in visible if b.kind != "hero"]
    base = public_base_url(request_origin(request))
    sections: list[HomepageSectionPublic] = []
    shown: set[uuid.UUID] = set()
    for block in ordered:
        config = stored_config(block.kind, block.config)
        if config is None:
            # Settings no longer usable (see stored_config): left out rather
            # than the whole page failing.
            continue
        section = await _to_public(session, block, base, localized=True)
        products = await _section_products(session, block, customer=customer)
        if block.kind == "personal":
            source = config["source"]
            if source == "current_order":
                if customer is None:
                    continue
                section.current_order = await current_order(session, customer.id)
                if section.current_order is None:
                    continue
            elif source != "recently_viewed":
                # Nothing bought yet, an empty wishlist: no empty section.
                if not products:
                    continue
                section.products = products
            sections.append(section)
            continue
        if products is not None:
            section.products = [p for p in products if p.id not in shown]
            shown.update(p.id for p in section.products)
        sections.append(section)
    return HomepagePublic(sections=sections, seo=await _seo(session, localized=True))


@router.get("/homepage", response_model=HomepagePublic)
async def get_homepage(request: Request, session: SessionDep) -> HomepagePublic:
    """The visitor's homepage. Reads no identity on purpose: the server render
    of the storefront is anonymous, and this answer must not depend on who
    asks (a signed-in customer asks ``/homepage/personal``)."""
    viewer = Viewer(signed_in=False, price_group_id=None, locale=request_locale())
    return await _page(request, session, viewer=viewer, customer=None)


@router.get("/homepage/personal", response_model=HomepagePublic)
async def get_personal_homepage(
    request: Request, response: Response, session: SessionDep, current_user: CurrentUser
) -> HomepagePublic:
    """The signed-in customer's homepage: the sections of their audience, the
    products at their prices. Never cached."""
    response.headers["Cache-Control"] = "no-store"
    group = await resolve_customer_group(session, current_user)
    viewer = Viewer(
        signed_in=True,
        price_group_id=group.id if group is not None else None,
        locale=request_locale(),
    )
    return await _page(request, session, viewer=viewer, customer=current_user)


@router.get("/homepage/announcement", response_model=HomepageSectionPublic | None)
async def get_announcement(
    request: Request, session: SessionDep
) -> HomepageSectionPublic | None:
    """The announcement shown above the header of every page (lot A3 / R4):
    the published one live now in the visitor's language, or nothing."""
    now = utcnow()
    viewer = Viewer(signed_in=False, price_group_id=None, locale=request_locale())
    rows = (
        await session.exec(
            select(HomepageBlock)
            .where(
                col(HomepageBlock.kind) == "announcement",
                col(HomepageBlock.is_active).is_(True),
                col(HomepageBlock.is_published).is_(True),
            )
            .order_by(col(HomepageBlock.position).asc())
        )
    ).all()
    for block in rows:
        if _is_live(block, now) and is_shown_to(block.audience, viewer):
            return await _to_public(
                session,
                block,
                public_base_url(request_origin(request)),
                localized=True,
            )
    return None


def _preview_refused() -> AppError:
    return AppError(
        code="homepage.preview_invalid",
        status_code=401,
        message="This preview link has expired: open the preview again from the admin.",
    )


async def _preview_admin(session: SessionDep, token: str | None) -> User:
    """The administrator a preview token was issued to, still active, still
    an administrator, still with the same security stamp."""
    if not token:
        raise _preview_refused()
    try:
        payload = decode_token(token)
    except InvalidTokenError:
        raise _preview_refused()
    if payload.get("type") != "homepage_preview":
        raise _preview_refused()
    try:
        user = await session.get(User, uuid.UUID(str(payload.get("sub"))))
    except ValueError:
        raise _preview_refused()
    stamp = str(payload.get("stp") or "")
    if (
        user is None
        or not user.is_superuser
        or not user.is_active
        or not stamp
        or not hmac.compare_digest(stamp, user.security_stamp or "")
    ):
        raise _preview_refused()
    return user


@router.post("/admin/homepage/preview-token", response_model=PreviewLink)
async def homepage_preview_token(admin: CurrentSuperUser) -> PreviewLink:
    """A link to see the homepage with its drafts, at a chosen date, as a
    chosen audience (lot A4 / R10). Valid 15 minutes."""
    token, expires = create_preview_token(admin.id, admin.security_stamp)
    return PreviewLink(
        token=token,
        expires_at=expires,
        storefront_url=settings.FRONTEND_HOST.rstrip("/"),
    )


@router.get("/homepage/preview", response_model=HomepagePublic)
async def get_homepage_preview(
    request: Request,
    response: Response,
    session: SessionDep,
    x_homepage_preview: Annotated[str | None, Header()] = None,
    at: Annotated[datetime.datetime | None, Query()] = None,
    scope: Annotated[Literal["guest", "customer"], Query()] = "guest",
    price_group_id: Annotated[uuid.UUID | None, Query()] = None,
) -> HomepagePublic:
    """The homepage as it will be: drafts included, at ``at``, for a visitor
    or a customer of a price group. Only with a valid preview token (header
    ``X-Homepage-Preview``); never cached. Prices stay the visitor's."""
    await _preview_admin(session, x_homepage_preview)
    response.headers["Cache-Control"] = "no-store"
    response.headers["X-Robots-Tag"] = "noindex"
    moment = as_utc(at) if at is not None else utcnow()
    viewer = Viewer(
        signed_in=scope == "customer",
        price_group_id=price_group_id if scope == "customer" else None,
        locale=request_locale(),
    )
    page = await _page(
        request, session, viewer=viewer, customer=None, now=moment, drafts=True
    )
    announcements = (
        await session.exec(
            select(HomepageBlock)
            .where(
                col(HomepageBlock.kind) == "announcement",
                col(HomepageBlock.is_active).is_(True),
            )
            .order_by(col(HomepageBlock.position).asc())
        )
    ).all()
    for block in announcements:
        if _is_live(block, moment) and is_shown_to(block.audience, viewer):
            page.announcement = await _to_public(
                session,
                block,
                public_base_url(request_origin(request)),
                localized=True,
            )
            break
    return page


@router.get("/admin/homepage/seo", response_model=HomepageSeoPublic)
async def get_homepage_seo(
    session: SessionDep, _admin: CurrentSuperUser
) -> HomepageSeoPublic:
    """The homepage title and description, with their translations."""
    return await _seo(session, localized=False) or HomepageSeoPublic()


@router.put("/admin/homepage/seo", response_model=HomepageSeoPublic)
async def save_homepage_seo(
    body: HomepageSeoWrite, session: SessionDep, admin: CurrentSuperUser
) -> HomepageSeoPublic:
    """Set the homepage title and description (empty: the storefront's)."""
    row = (await session.exec(select(HomepageSeo))).first()
    values = {"title": body.title.strip(), "description": body.description.strip()}
    try:
        translations = clean_translations(
            body.translations,
            previous=row.translations if row else None,
            source_values=values,
            fields=HOMEPAGE_SEO_FIELDS,
        )
    except InvalidTranslations as exc:
        raise AppError(
            code="homepage.translations",
            status_code=400,
            message="Invalid translations.",
            details={"field": "translations", "problem": str(exc)},
        ) from exc
    if row is None:
        row = HomepageSeo()
    row.title = values["title"]
    row.description = values["description"]
    row.translations = translations
    row.modify_at = utcnow()
    row.modify_by_id = admin.id
    session.add(row)
    await session.commit()
    return await _seo(session, localized=False) or HomepageSeoPublic()


@router.get("/admin/homepage-blocks", response_model=list[HomepageSectionPublic])
async def list_blocks(
    request: Request, session: SessionDep, _admin: CurrentSuperUser
) -> list[HomepageSectionPublic]:
    """Every section, published or not, in display order."""
    rows = (
        await session.exec(
            select(HomepageBlock)
            .where(col(HomepageBlock.is_active).is_(True))
            .order_by(
                col(HomepageBlock.position).asc(),
                col(HomepageBlock.title).asc(),
            )
        )
    ).all()
    base = public_base_url(request_origin(request))
    return [await _to_public(session, b, base) for b in rows]


def _overlaps(
    a_start: datetime.datetime | None,
    a_end: datetime.datetime | None,
    b_start: datetime.datetime | None,
    b_end: datetime.datetime | None,
) -> bool:
    """Two publication windows share at least one instant (None = open end)."""
    starts_before_other_ends = (
        b_end is None or a_start is None or as_utc(a_start) < as_utc(b_end)
    )
    ends_after_other_starts = (
        a_end is None or b_start is None or as_utc(a_end) > as_utc(b_start)
    )
    return starts_before_other_ends and ends_after_other_starts


async def _refuse_second_live_hero(
    session: SessionDep, body: HomepageBlockWrite, *, exclude_id: uuid.UUID | None
) -> None:
    """One published hero per period and per audience: the storefront shows a
    single one, by position, so a second live hero for the same visitors
    would silently never appear (03/10/2026). Heroes for audiences no visitor
    shares (visitors / customers, two price groups) may overlap in time."""
    if body.kind not in ("hero", "announcement") or not body.is_published:
        return
    others = (
        await session.exec(
            select(HomepageBlock).where(
                col(HomepageBlock.kind) == body.kind,
                col(HomepageBlock.is_published).is_(True),
                col(HomepageBlock.is_active).is_(True),
            )
        )
    ).all()
    for other in others:
        if exclude_id is not None and other.id == exclude_id:
            continue
        if _overlaps(
            body.starts_at, body.ends_at, other.starts_at, other.ends_at
        ) and audiences_overlap(body.audience, other.audience):
            if body.kind == "announcement":
                raise AppError(
                    code="homepage.announcement.conflict",
                    status_code=409,
                    message=(
                        "Another published announcement already covers this period: “{other_title}”. Only one is shown at a time."
                    ),
                    details={
                        "field": "is_published",
                        "other_id": str(other.id),
                        "other_title": other.title,
                    },
                )
            raise AppError(
                code="homepage.hero.conflict",
                status_code=409,
                message=(
                    "Another published hero already covers this period: “{other_title}”. Only one hero is shown: unpublish it or give them dates that do not overlap."
                ),
                details={
                    "field": "is_published",
                    "other_id": str(other.id),
                    "other_title": other.title,
                },
            )


async def _check_media(session: SessionDep, media_id: uuid.UUID | None) -> None:
    if media_id is None:
        return
    media = await session.get(MediaAsset, media_id)
    if media is None or not media.is_active:
        raise _invalid("Image not found.", "homepage.media", "media_id")


async def _prepare(session: SessionDep, body: HomepageBlockWrite) -> None:
    """Every check of a create or a replace; ``config``, ``audience`` and
    ``items`` are replaced by their cleaned values."""
    _validate(body)
    body.config, body.audience = await _clean_sections_fields(session, body)
    manual_products = (
        body.kind == "collection" and body.config.get("source") == "manual"
    )
    manual_categories = (
        body.kind == "categories" and body.config.get("mode") == "manual"
    )
    manual_brands = body.kind == "brand_strip" and body.config.get("mode") == "manual"
    if not (manual_products or manual_categories or manual_brands):
        body.items = []
        return
    field = (
        "product_id"
        if manual_products
        else "category_id"
        if manual_categories
        else "brand_id"
    )
    model: type[Product] | type[Category] | type[Brand] = (
        Product if manual_products else Category if manual_categories else Brand
    )
    seen: set[uuid.UUID] = set()
    cleaned = []
    for item in body.items:
        target = getattr(item, field)
        if target is None or target in seen:
            raise _invalid("Invalid list of the section.", "homepage.items", "items")
        if await session.get(model, target) is None:
            raise _invalid("Invalid list of the section.", "homepage.items", "items")
        seen.add(target)
        cleaned.append(
            HomepageItemWrite(
                **{field: target},
                label=(item.label or "").strip() or None,
            )
        )
    body.items = cleaned


async def _save_items(
    session: SessionDep, block_id: uuid.UUID, body: HomepageBlockWrite
) -> None:
    for old in await section_items(session, block_id):
        await session.delete(old)
    for position, item in enumerate(body.items):
        session.add(
            HomepageBlockItem(
                block_id=block_id,
                position=position,
                product_id=item.product_id,
                category_id=item.category_id,
                brand_id=item.brand_id,
                label=item.label,
            )
        )


@router.post(
    "/admin/homepage-blocks", response_model=HomepageSectionPublic, status_code=201
)
async def create_block(
    body: HomepageBlockWrite,
    request: Request,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> HomepageSectionPublic:
    """Add a section, at the end of the page (``position`` is ignored: the
    order is set by ``PUT /admin/homepage-blocks/order``)."""
    await _prepare(session, body)
    await _refuse_second_live_hero(session, body, exclude_id=None)
    await _check_media(session, body.media_id)
    data = _with_translations(body, previous=None)
    last = (
        await session.exec(
            select(HomepageBlock.position)
            .where(col(HomepageBlock.is_active).is_(True))
            .order_by(col(HomepageBlock.position).desc())
            .limit(1)
        )
    ).first()
    data["position"] = (last + 1) if last is not None else 0
    data.pop("items", None)
    block = HomepageBlock(**data, created_at=utcnow(), created_by_id=admin.id)
    session.add(block)
    await session.flush()
    await _save_items(session, block.id, body)
    await session.commit()
    await session.refresh(block)
    return await _to_public(session, block, public_base_url(request_origin(request)))


async def _block_or_404(session: SessionDep, block_id: uuid.UUID) -> HomepageBlock:
    block = await session.get(HomepageBlock, block_id)
    if block is None or not block.is_active:
        raise AppError(
            code="homepage.not_found",
            status_code=404,
            message="Block not found.",
            details={"id": str(block_id)},
        )
    return block


@router.put("/admin/homepage-blocks/order", response_model=list[HomepageSectionPublic])
async def reorder_blocks(
    body: HomepageOrder,
    request: Request,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> list[HomepageSectionPublic]:
    """Put every section in the given order, in one transaction. The list must
    name each active section once: a page changed meanwhile (a section added
    or removed in another tab) is refused rather than half applied."""
    rows = (
        await session.exec(
            select(HomepageBlock).where(col(HomepageBlock.is_active).is_(True))
        )
    ).all()
    by_id = {row.id: row for row in rows}
    if len(body.ids) != len(set(body.ids)) or set(body.ids) != set(by_id):
        raise AppError(
            code="homepage.order_conflict",
            status_code=409,
            message="The page changed meanwhile: reload it and order the sections again.",
            details={"field": "ids"},
        )
    now = utcnow()
    for position, block_id in enumerate(body.ids):
        block = by_id[block_id]
        if block.position != position:
            block.position = position
            block.modify_at = now
            block.modify_by_id = admin.id
            session.add(block)
    await session.commit()
    base = public_base_url(request_origin(request))
    ordered = [by_id[block_id] for block_id in body.ids]
    for block in ordered:
        await session.refresh(block)
    return [await _to_public(session, block, base) for block in ordered]


@router.put("/admin/homepage-blocks/{block_id}", response_model=HomepageSectionPublic)
async def replace_block(
    block_id: uuid.UUID,
    body: HomepageBlockWrite,
    request: Request,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> HomepageSectionPublic:
    """Replace every field of a section but its place in the page."""
    block = await _block_or_404(session, block_id)
    await _prepare(session, body)
    await _refuse_second_live_hero(session, body, exclude_id=block.id)
    await _check_media(session, body.media_id)
    data = _with_translations(body, previous=block.translations)
    data.pop("position", None)
    data.pop("items", None)
    for field, value in data.items():
        setattr(block, field, value)
    await _save_items(session, block.id, body)
    block.modify_at = utcnow()
    block.modify_by_id = admin.id
    session.add(block)
    await session.commit()
    await session.refresh(block)
    return await _to_public(session, block, public_base_url(request_origin(request)))


@router.delete("/admin/homepage-blocks/{block_id}", status_code=204)
async def delete_block(
    block_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> None:
    """Remove a section (its image stays in the media library)."""
    block = await _block_or_404(session, block_id)
    await session.delete(block)
    await session.commit()
