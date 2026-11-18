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
import uuid
from typing import Any

from fastapi import APIRouter, Request, Response
from pydantic import BaseModel
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, CurrentUser, SessionDep
from app.api.routes.media import request_origin
from app.core.content_i18n import (
    HOMEPAGE_BLOCK_FIELDS,
    InvalidTranslations,
    clean_translations,
    localize_all,
)
from app.core.datetimes import as_utc, utcnow
from app.core.errors import AppError
from app.core.i18n import request_locale
from app.features.content.homepage_sections import (
    InvalidSection,
    Viewer,
    audiences_overlap,
    clean_audience,
    clean_config,
    is_shown_to,
)
from app.features.content.models import (
    HOMEPAGE_BLOCK_KINDS,
    HOMEPAGE_BUILTIN_KINDS,
    HomepageBlock,
    HomepageBlockPublic,
    HomepageBlockWrite,
    HomepageImage,
    HomepageOrder,
)
from app.features.inventory.services.availability import publish_with_availability
from app.features.media.models import MediaAsset
from app.features.media.service import public_base_url, to_public
from app.features.product.crud.product import crud_product
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import ProductPublic
from app.features.product.services.group_pricing import resolve_customer_group
from app.features.product.services.popularity import popular_products

router = APIRouter(tags=["homepage"])


class HomepageSectionPublic(HomepageBlockPublic):
    """A section of the storefront homepage, with its products when it shows
    some (featured, most viewed)."""

    products: list[ProductPublic] | None = None


class HomepagePublic(BaseModel):
    """The storefront homepage: its sections in display order (the hero, if
    any, first)."""

    sections: list[HomepageSectionPublic] = []


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
    if body.kind not in HOMEPAGE_BUILTIN_KINDS and not body.title.strip():
        raise _invalid("A title is required.", "homepage.title", "title")
    link = (body.cta_link or "").strip()
    # A storefront path or an https URL: never javascript: or a protocol-relative
    # URL that would take the visitor elsewhere unnoticed.
    if link and not (
        (link.startswith("/") and not link.startswith("//"))
        or link.startswith("https://")
    ):
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
        raise _invalid(
            f"Invalid translations: {exc}", "homepage.translations", "translations"
        )
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
    return item


def _is_live(block: HomepageBlock, now: datetime.datetime) -> bool:
    return (block.starts_at is None or as_utc(block.starts_at) <= now) and (
        block.ends_at is None or as_utc(block.ends_at) > now
    )


async def _section_products(
    session: SessionDep, block: HomepageBlock, *, customer: Any
) -> list[ProductPublic] | None:
    """The products of a product section, priced for ``customer`` (a user,
    or None for a visitor: the default group's prices)."""
    config = clean_config(block.kind, block.config)
    if block.kind == "featured":
        products = await crud_product.get_featured(
            session=session, limit=config["limit"]
        )
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


async def _page(
    request: Request, session: SessionDep, *, viewer: Viewer, customer: Any
) -> HomepagePublic:
    """The sections ``viewer`` sees, in order: the first hero, then the rest.
    Two sections showing the same products (featured, then most viewed) do
    not show a product twice."""
    now = utcnow()
    rows = (
        await session.exec(
            select(HomepageBlock)
            .where(
                col(HomepageBlock.is_active).is_(True),
                col(HomepageBlock.is_published).is_(True),
            )
            .order_by(col(HomepageBlock.position).asc(), col(HomepageBlock.title).asc())
        )
    ).all()
    visible = [b for b in rows if _is_live(b, now) and is_shown_to(b.audience, viewer)]
    hero = next((b for b in visible if b.kind == "hero"), None)
    ordered = ([hero] if hero else []) + [b for b in visible if b.kind != "hero"]
    base = public_base_url(request_origin(request))
    sections: list[HomepageSectionPublic] = []
    shown: set[uuid.UUID] = set()
    for block in ordered:
        section = await _to_public(session, block, base, localized=True)
        products = await _section_products(session, block, customer=customer)
        if products is not None:
            section.products = [p for p in products if p.id not in shown]
            shown.update(p.id for p in section.products)
        sections.append(section)
    return HomepagePublic(sections=sections)


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
    if body.kind != "hero" or not body.is_published:
        return
    others = (
        await session.exec(
            select(HomepageBlock).where(
                col(HomepageBlock.kind) == "hero",
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
    """Every check of a create or a replace; ``config`` and ``audience`` are
    replaced by their cleaned values."""
    _validate(body)
    body.config, body.audience = await _clean_sections_fields(session, body)


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
    block = HomepageBlock(**data, created_at=utcnow(), created_by_id=admin.id)
    session.add(block)
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
    for field, value in data.items():
        setattr(block, field, value)
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
