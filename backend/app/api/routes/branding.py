"""Public brand assets derived from the media library (R9 / T9).

``/branding/{asset_id}/icon-{size}.png``, ``/branding/{asset_id}/site.webmanifest``
and ``/branding/{asset_id}/logo.webp``: the asset id is in the URL, so a new
icon or logo is a new URL and the old one may be cached forever.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Request, Response

from app.api.deps import SessionDep
from app.api.routes.media import request_origin
from app.core.errors import AppError
from app.features.attachment.storage.factory import get_file_storage
from app.features.media.branding import (
    ICON_SIZES,
    logo_variant,
    manifest,
    render_icon,
)
from app.features.media.models import MediaAsset
from app.features.media.service import public_base_url

router = APIRouter(prefix="/branding", tags=["branding"], include_in_schema=False)

_IMMUTABLE = "public, max-age=31536000, immutable"


def _not_found(asset_id: uuid.UUID) -> AppError:
    return AppError(
        code="media.not_found",
        status_code=404,
        message="Image introuvable",
        details={"asset_id": str(asset_id)},
    )


async def _active_asset(session: SessionDep, asset_id: uuid.UUID) -> MediaAsset:
    asset = await session.get(MediaAsset, asset_id)
    if asset is None or not asset.is_active:
        raise _not_found(asset_id)
    return asset


@router.get("/{asset_id}/icon-{size}.png")
async def icon(asset_id: uuid.UUID, size: int, session: SessionDep) -> Response:
    """One square PNG size of the site icon."""
    if size not in ICON_SIZES:
        raise _not_found(asset_id)
    asset = await _active_asset(session, asset_id)
    try:
        data = await render_icon(asset, size)
    except ValueError as exc:
        raise _not_found(asset_id) from exc
    return Response(
        content=data,
        media_type="image/png",
        headers={"Cache-Control": _IMMUTABLE, "X-Content-Type-Options": "nosniff"},
    )


@router.get("/{asset_id}/site.webmanifest")
async def webmanifest(
    asset_id: uuid.UUID, request: Request, session: SessionDep
) -> Response:
    """The web app manifest naming the shop and its icon sizes."""
    asset = await _active_asset(session, asset_id)
    data = await manifest(session, asset, public_base_url(request_origin(request)))
    return Response(
        content=data,
        media_type="application/manifest+json",
        headers={"Cache-Control": "public, max-age=3600"},
    )


@router.get("/{asset_id}/logo.webp")
async def logo(asset_id: uuid.UUID, session: SessionDep) -> Response:
    """The logo at a size fit for a header or an e-mail."""
    asset = await _active_asset(session, asset_id)
    variant = logo_variant(asset)
    if variant is None:
        raise _not_found(asset_id)
    data = await get_file_storage().get_bytes(key=str(variant["key"]))
    return Response(
        content=data,
        media_type="image/webp",
        headers={"Cache-Control": _IMMUTABLE, "X-Content-Type-Options": "nosniff"},
    )
