"""Site icon and logo chosen in the back-office (R9 / T9).

Two settings hold the id of a media-library asset: ``shop_logo_media_id``
(the header of the storefront, the e-mails, the PDFs) and
``shop_icon_media_id`` (favicon and home-screen icon). From the icon the API
derives the square PNG sizes browsers ask for and a ``site.webmanifest``;
the storefront only has to point its ``<link rel="icon">`` tags at them.
Nothing configured = the storefront's bundled icons and the shop name as
text, exactly as before.
"""

from __future__ import annotations

import io
import json
import uuid
from typing import Any

from PIL import Image
from pydantic import BaseModel
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core import runtime_settings
from app.core.config import settings
from app.features.attachment.storage.factory import get_file_storage
from app.features.media.models import MediaAsset
from app.features.media.service import public_base_url

LOGO_SETTING = "shop_logo_media_id"
ICON_SETTING = "shop_icon_media_id"
#: Favicon, favicon HD, Apple touch icon, manifest icons.
ICON_SIZES: tuple[int, ...] = (16, 32, 180, 192, 512)
#: Smallest logo variant served to e-mails and headers (a 2× 200 px display).
LOGO_MIN_WIDTH = 480


class BrandingImage(BaseModel):
    """An image of the brand: the logo as the storefront shows it."""

    src: str
    srcset: str | None = None
    width: int
    height: int


class BrandingIcon(BaseModel):
    """Where the icon sizes live: ``{base}/icon-{size}.png`` and the manifest."""

    base: str
    sizes: list[int]
    manifest: str


class ShopBranding(BaseModel):
    """Logo and icon of the shop, for ``GET /system/config``."""

    logo: BrandingImage | None = None
    icon: BrandingIcon | None = None


def _asset_uuid(raw: Any) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(raw)) if raw else None
    except (TypeError, ValueError):
        return None


async def _asset(session: AsyncSession, raw_id: Any) -> MediaAsset | None:
    asset_id = _asset_uuid(raw_id)
    if asset_id is None:
        return None
    asset = await session.get(MediaAsset, asset_id)
    return asset if asset is not None and asset.is_active else None


def logo_variant(asset: MediaAsset) -> dict[str, Any] | None:
    """The variant shown as logo: the smallest at least ``LOGO_MIN_WIDTH`` wide,
    else the largest there is."""
    variants = sorted(asset.variants or [], key=lambda v: int(v["width"]))
    if not variants:
        return None
    for variant in variants:
        if int(variant["width"]) >= LOGO_MIN_WIDTH:
            return variant
    return variants[-1]


def largest_variant(asset: MediaAsset) -> dict[str, Any] | None:
    variants = sorted(asset.variants or [], key=lambda v: int(v["width"]))
    return variants[-1] if variants else None


def branding_base(base_url: str, asset_id: uuid.UUID) -> str:
    return f"{base_url}{settings.API_V1_STR}/branding/{asset_id}"


def logo_url(base_url: str, asset_id: uuid.UUID) -> str:
    """Stable URL of the logo (served by ``GET /branding/{id}/logo.webp``)."""
    return f"{branding_base(base_url, asset_id)}/logo.webp"


def logo_url_from_settings(base_url: str | None = None) -> str | None:
    """Synchronous logo URL for the e-mail and PDF renderers (``peek``)."""
    asset_id = _asset_uuid(runtime_settings.peek(LOGO_SETTING))
    if asset_id is None:
        return None
    return logo_url(public_base_url(base_url), asset_id)


async def shop_branding(session: AsyncSession, base_url: str) -> ShopBranding:
    """What the storefront needs to show the brand."""
    branding = ShopBranding()
    logo = await _asset(session, await runtime_settings.get(LOGO_SETTING, session))
    if logo is not None:
        variant = logo_variant(logo)
        if variant is not None:
            from app.features.media.service import to_public

            described = to_public(logo, base_url)
            branding.logo = BrandingImage(
                src=logo_url(base_url, logo.id),
                srcset=described.srcset,
                width=int(variant["width"]),
                height=int(variant["height"]),
            )
    icon = await _asset(session, await runtime_settings.get(ICON_SETTING, session))
    if icon is not None and largest_variant(icon) is not None:
        base = branding_base(base_url, icon.id)
        branding.icon = BrandingIcon(
            base=base, sizes=list(ICON_SIZES), manifest=f"{base}/site.webmanifest"
        )
    return branding


async def render_icon(asset: MediaAsset, size: int) -> bytes:
    """A square PNG of ``size`` px cut from the asset (centre crop, cover)."""
    variant = largest_variant(asset)
    if variant is None:
        raise ValueError("asset has no variant")
    data = await get_file_storage().get_bytes(key=str(variant["key"]))
    with Image.open(io.BytesIO(data)) as source:
        image = source.convert("RGBA")
        side = min(image.width, image.height)
        left = (image.width - side) // 2
        top = (image.height - side) // 2
        square = image.crop((left, top, left + side, top + side))
        resized = square.resize((size, size), Image.Resampling.LANCZOS)
        buffer = io.BytesIO()
        resized.save(buffer, format="PNG", optimize=True)
        return buffer.getvalue()


async def manifest(session: AsyncSession, asset: MediaAsset, base_url: str) -> bytes:
    """``site.webmanifest`` pointing at the derived icon sizes."""
    base = branding_base(base_url, asset.id)
    name = str(await runtime_settings.get("shop_name", session) or "")
    payload = {
        "name": name,
        "short_name": name[:12] if name else "",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#ffffff",
        "theme_color": "#ffffff",
        "icons": [
            {
                "src": f"{base}/icon-{size}.png",
                "sizes": f"{size}x{size}",
                "type": "image/png",
            }
            for size in (192, 512)
        ],
    }
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


__all__ = [
    "ICON_SETTING",
    "ICON_SIZES",
    "LOGO_SETTING",
    "BrandingIcon",
    "BrandingImage",
    "ShopBranding",
    "logo_url",
    "logo_url_from_settings",
    "logo_variant",
    "manifest",
    "render_icon",
    "shop_branding",
]
