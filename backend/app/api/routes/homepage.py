"""Storefront homepage: its hero and banners, edited from the admin.

``GET /homepage`` is public and returns only what is published and within its
dates; the admin routes list, create, replace and delete blocks.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from fastapi import APIRouter, Request
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.api.routes.media import request_origin
from app.core.content_i18n import (
    HOMEPAGE_BLOCK_FIELDS,
    InvalidTranslations,
    clean_translations,
    localize_all,
)
from app.core.datetimes import as_utc, utcnow
from app.core.errors import AppError
from app.features.content.models import (
    HOMEPAGE_BLOCK_KINDS,
    HomepageBlock,
    HomepageBlockPublic,
    HomepageBlockWrite,
    HomepageImage,
    HomepagePublic,
)
from app.features.media.models import MediaAsset
from app.features.media.service import public_base_url, to_public

router = APIRouter(tags=["homepage"])


def _invalid(message: str, code: str, field: str) -> AppError:
    return AppError(
        code=code, status_code=400, message=message, details={"field": field}
    )


def _validate(body: HomepageBlockWrite) -> None:
    if body.kind not in HOMEPAGE_BLOCK_KINDS:
        raise _invalid(
            f"Type inconnu : {body.kind} (hero ou banner).", "homepage.kind", "kind"
        )
    link = (body.cta_link or "").strip()
    # A storefront path or an https URL: never javascript: or a protocol-relative
    # URL that would take the visitor elsewhere unnoticed.
    if link and not (
        (link.startswith("/") and not link.startswith("//"))
        or link.startswith("https://")
    ):
        raise _invalid(
            "Lien : un chemin du site (/catalogue…) ou une adresse https://.",
            "homepage.link",
            "cta_link",
        )
    image = (body.image_url or "").strip()
    if image and not image.startswith("https://") and not image.startswith("http://"):
        raise _invalid(
            "Image : une adresse http(s) complète.", "homepage.image", "image_url"
        )
    if (
        body.starts_at
        and body.ends_at
        and as_utc(body.ends_at) <= as_utc(body.starts_at)
    ):
        raise _invalid("La fin doit suivre le début.", "homepage.dates", "ends_at")


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
            f"Traductions invalides : {exc}", "homepage.translations", "translations"
        )
    return data


async def _to_public(
    session: SessionDep, block: HomepageBlock, base_url: str, *, localized: bool = False
) -> HomepageBlockPublic:
    item = HomepageBlockPublic.model_validate(block, from_attributes=True)
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


@router.get("/homepage", response_model=HomepagePublic)
async def get_homepage(request: Request, session: SessionDep) -> HomepagePublic:
    """Published blocks whose dates include now: the first hero, then banners."""
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
    base = public_base_url(request_origin(request))
    visible = [
        b
        for b in rows
        if (b.starts_at is None or as_utc(b.starts_at) <= now)
        and (b.ends_at is None or as_utc(b.ends_at) > now)
    ]
    hero = next((b for b in visible if b.kind == "hero"), None)
    return HomepagePublic(
        hero=await _to_public(session, hero, base, localized=True) if hero else None,
        banners=[
            await _to_public(session, b, base, localized=True)
            for b in visible
            if b.kind == "banner"
        ],
    )


@router.get("/admin/homepage-blocks", response_model=list[HomepageBlockPublic])
async def list_blocks(
    request: Request, session: SessionDep, _admin: CurrentSuperUser
) -> list[HomepageBlockPublic]:
    """Every block, published or not, in display order."""
    rows = (
        await session.exec(
            select(HomepageBlock)
            .where(col(HomepageBlock.is_active).is_(True))
            .order_by(
                col(HomepageBlock.kind).desc(),
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
    """One published hero per period: the storefront shows a single one, by
    position, so a second live hero would silently never appear (03/10/2026)."""
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
        if _overlaps(body.starts_at, body.ends_at, other.starts_at, other.ends_at):
            raise AppError(
                code="homepage.hero.conflict",
                status_code=409,
                message=(
                    f"Un autre hero publié couvre déjà cette période : « {other.title} ». "
                    "Un seul hero s'affiche ; dépubliez-le, ou donnez aux deux des "
                    "dates qui ne se chevauchent pas."
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
        raise _invalid("Image introuvable.", "homepage.media", "media_id")


@router.post(
    "/admin/homepage-blocks", response_model=HomepageBlockPublic, status_code=201
)
async def create_block(
    body: HomepageBlockWrite,
    request: Request,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> HomepageBlockPublic:
    """Add a hero or a banner."""
    _validate(body)
    await _refuse_second_live_hero(session, body, exclude_id=None)
    await _check_media(session, body.media_id)
    data = _with_translations(body, previous=None)
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
            message="Bloc introuvable",
            details={"id": str(block_id)},
        )
    return block


@router.put("/admin/homepage-blocks/{block_id}", response_model=HomepageBlockPublic)
async def replace_block(
    block_id: uuid.UUID,
    body: HomepageBlockWrite,
    request: Request,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> HomepageBlockPublic:
    """Replace every field of a block."""
    block = await _block_or_404(session, block_id)
    _validate(body)
    await _refuse_second_live_hero(session, body, exclude_id=block.id)
    await _check_media(session, body.media_id)
    for field, value in _with_translations(body, previous=block.translations).items():
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
    """Remove a block (its image stays in the media library)."""
    block = await _block_or_404(session, block_id)
    await session.delete(block)
    await session.commit()
