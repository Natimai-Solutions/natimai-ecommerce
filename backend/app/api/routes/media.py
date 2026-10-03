"""Public images: served to browsers, uploaded and managed from the admin.

``GET /media/{asset_id}/{width}.webp`` is public and cacheable forever (the
key never changes content: a new upload is a new asset). The admin routes
upload, list, relabel and delete assets; a delete is refused while a
homepage block, a product, a category or an editable page still uses it.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, File, Form, Request, Response, UploadFile
from sqlmodel import col, func, or_, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.features.attachment.storage.factory import get_file_storage
from app.features.content.models import ContentPage, HomepageBlock
from app.features.media.models import MediaAsset, MediaAssetPublic, MediaAssetUpdate
from app.features.media.service import (
    delete_stored_variants,
    ingest_image,
    public_base_url,
    to_public,
    validate_kind,
)
from app.features.product.models.category import Category
from app.features.product.models.product import Product

router = APIRouter(tags=["media"])

_VARIANT_NAME = re.compile(r"^(\d{2,5})\.webp$")
# The key never changes content: browsers and CDNs may keep it for a year.
_IMMUTABLE_CACHE = "public, max-age=31536000, immutable"


def request_origin(request: Request) -> str:
    """Scheme and host the request came in on (development fallback)."""
    return f"{request.url.scheme}://{request.url.netloc}"


def _not_found(asset_id: uuid.UUID) -> AppError:
    return AppError(
        code="media.not_found",
        status_code=404,
        message="Image introuvable",
        details={"id": str(asset_id)},
    )


@router.get("/media/{asset_id}/{name}", include_in_schema=False)
async def serve_media(asset_id: uuid.UUID, name: str, session: SessionDep) -> Response:
    """One stored variant, as ``image/webp``. Only keys recorded on an active
    asset are served: the route is not a window onto the whole storage."""
    match = _VARIANT_NAME.match(name)
    asset = await session.get(MediaAsset, asset_id)
    if match is None or asset is None or not asset.is_active:
        raise _not_found(asset_id)
    key = next(
        (
            str(v["key"])
            for v in asset.variants or []
            if int(v["width"]) == int(match.group(1))
        ),
        None,
    )
    if key is None:
        raise _not_found(asset_id)
    data = await get_file_storage().get_bytes(key=key)
    return Response(
        content=data,
        media_type="image/webp",
        headers={
            "Cache-Control": _IMMUTABLE_CACHE,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/admin/media", response_model=MediaAssetPublic, status_code=201)
async def upload_media(
    request: Request,
    session: SessionDep,
    admin: CurrentSuperUser,
    file: Annotated[UploadFile, File()],
    kind: Annotated[str, Form()] = "other",
    alt: Annotated[str | None, Form()] = None,
) -> MediaAssetPublic:
    """Upload an image: scanned, re-encoded to WebP widths, then stored."""
    validate_kind(kind)
    data = await file.read()
    asset_id = uuid.uuid4()
    variants, width, height, size = await ingest_image(data, asset_id=asset_id)
    asset = MediaAsset(
        id=asset_id,
        kind=kind,
        original_filename=(file.filename or None),
        alt=(alt or "").strip() or None,
        width=width,
        height=height,
        size_bytes=size,
        variants=variants,
        created_at=utcnow(),
        created_by_id=admin.id,
    )
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return to_public(asset, public_base_url(request_origin(request)))


@router.get("/admin/media", response_model=list[MediaAssetPublic])
async def list_media(
    request: Request,
    session: SessionDep,
    _admin: CurrentSuperUser,
    kind: str | None = None,
    limit: int = 60,
    offset: int = 0,
) -> list[MediaAssetPublic]:
    """Latest images first, optionally for one kind."""
    statement = select(MediaAsset).where(col(MediaAsset.is_active).is_(True))
    if kind:
        statement = statement.where(col(MediaAsset.kind) == kind)
    statement = (
        statement.order_by(col(MediaAsset.created_at).desc().nulls_last())
        .offset(max(offset, 0))
        .limit(min(max(limit, 1), 200))
    )
    base = public_base_url(request_origin(request))
    return [to_public(a, base) for a in (await session.exec(statement)).all()]


@router.get("/admin/media/{asset_id}", response_model=MediaAssetPublic)
async def get_media(
    asset_id: uuid.UUID, request: Request, session: SessionDep, _admin: CurrentSuperUser
) -> MediaAssetPublic:
    """One image, by id (the admin forms read the alt text of an image_url)."""
    asset = await session.get(MediaAsset, asset_id)
    if asset is None or not asset.is_active:
        raise _not_found(asset_id)
    return to_public(asset, public_base_url(request_origin(request)))


@router.patch("/admin/media/{asset_id}", response_model=MediaAssetPublic)
async def update_media(
    asset_id: uuid.UUID,
    payload: MediaAssetUpdate,
    request: Request,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> MediaAssetPublic:
    """Change the alternative text or the kind."""
    asset = await session.get(MediaAsset, asset_id)
    if asset is None or not asset.is_active:
        raise _not_found(asset_id)
    changes = payload.model_dump(exclude_unset=True)
    if "kind" in changes and changes["kind"] is not None:
        asset.kind = validate_kind(changes["kind"])
    if "alt" in changes:
        asset.alt = (changes["alt"] or "").strip() or None
    asset.modify_at = utcnow()
    asset.modify_by_id = admin.id
    session.add(asset)
    await session.commit()
    await session.refresh(asset)
    return to_public(asset, public_base_url(request_origin(request)))


async def media_usages(session: SessionDep, asset_id: uuid.UUID) -> list[str]:
    """Where an image is still in use, as human labels."""
    pattern = f"%/media/{asset_id}/%"
    usages: list[str] = []
    blocks = (
        await session.exec(
            select(HomepageBlock.title).where(
                or_(
                    col(HomepageBlock.media_id) == asset_id,
                    col(HomepageBlock.image_url).like(pattern),
                )
            )
        )
    ).all()
    usages += [f"Accueil : {title}" for title in blocks]
    products = (
        await session.exec(
            select(func.count())
            .select_from(Product)
            .where(col(Product.image_url).like(pattern))
        )
    ).one()
    if products:
        usages.append(f"{products} produit(s)")
    categories = (
        await session.exec(
            select(Category.name).where(col(Category.image_url).like(pattern))
        )
    ).all()
    usages += [f"Catégorie : {name}" for name in categories]
    pages = (
        await session.exec(
            select(ContentPage.slug).where(col(ContentPage.body_html).like(pattern))
        )
    ).all()
    usages += [f"Page : {slug}" for slug in pages]
    return usages


@router.delete("/admin/media/{asset_id}", status_code=204)
async def delete_media(
    asset_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> None:
    """Delete an unused image and its stored files."""
    asset = await session.get(MediaAsset, asset_id)
    if asset is None:
        raise _not_found(asset_id)
    usages = await media_usages(session, asset_id)
    if usages:
        raise AppError(
            code="media.in_use",
            status_code=409,
            message="Image encore utilisée : " + ", ".join(usages[:5]),
            details={"usages": usages},
        )
    await delete_stored_variants(asset)
    await session.delete(asset)
    await session.commit()
