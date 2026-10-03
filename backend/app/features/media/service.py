"""Upload, re-encode, store and describe public images.

Every upload goes through the same steps, all server side:

1. size cap, then antivirus scan of the raw bytes (same scanner as the
   payment attachments — mandatory outside local development);
2. decoding with Pillow, restricted to JPEG / PNG / WebP, with a pixel cap
   against decompression bombs;
3. orientation from EXIF applied, then every metadata dropped by the
   re-encoding;
4. a few WebP widths (never upscaled), stored under
   ``media/{asset_id}/{width}.webp``.
"""

from __future__ import annotations

import io
import re
import uuid
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import anyio
from PIL import Image, ImageOps, UnidentifiedImageError
from sqlmodel import col, select

from app.core.config import settings
from app.core.errors import AppError
from app.features.attachment.antivirus.factory import get_antivirus_scanner
from app.features.attachment.storage.factory import get_file_storage
from app.features.media.models import (
    MEDIA_KINDS,
    MediaAsset,
    MediaAssetPublic,
    MediaVariantPublic,
)

#: Formats accepted as input (Pillow format names).
ACCEPTED_FORMATS: frozenset[str] = frozenset({"JPEG", "PNG", "WEBP"})
#: Widths produced, in pixels; the original width stands in for larger ones.
VARIANT_WIDTHS: tuple[int, ...] = (480, 960, 1600)
#: Above this many pixels an image is refused before being decoded.
MAX_PIXELS = 40_000_000
WEBP_QUALITY = 82

MEDIA_PREFIX = "media"


@dataclass(slots=True)
class EncodedVariant:
    """One re-encoded size, ready to store."""

    width: int
    height: int
    data: bytes


def _invalid(message: str, code: str = "media.invalid") -> AppError:
    return AppError(code=code, status_code=400, message=message)


def encode_variants(data: bytes) -> list[EncodedVariant]:
    """Decode an uploaded image and re-encode it as WebP at a few widths.

    Raises ``AppError`` (400) on an unreadable, unsupported or oversized
    image. Pure CPU work: call it from a worker thread.
    """
    try:
        with Image.open(io.BytesIO(data)) as probe:
            fmt = probe.format
            width, height = probe.size
            if fmt not in ACCEPTED_FORMATS:
                raise _invalid(
                    "Format non accepté : JPEG, PNG ou WebP uniquement.",
                    "media.format",
                )
            if width * height > MAX_PIXELS:
                raise _invalid(
                    "Image trop grande (plus de 40 millions de pixels).",
                    "media.too_many_pixels",
                )
            probe.verify()
        with Image.open(io.BytesIO(data)) as source:
            image = ImageOps.exif_transpose(source)
            image.load()
    except AppError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise _invalid("Fichier illisible : ce n'est pas une image valide.") from None

    has_alpha = image.mode in ("RGBA", "LA") or (
        image.mode == "P" and "transparency" in image.info
    )
    image = image.convert("RGBA" if has_alpha else "RGB")

    widths = sorted(
        {w for w in VARIANT_WIDTHS if w < image.width}
        | {min(image.width, VARIANT_WIDTHS[-1])}
    )
    variants: list[EncodedVariant] = []
    for target in widths:
        if target == image.width:
            resized = image
        else:
            ratio = target / image.width
            resized = image.resize(
                (target, max(1, round(image.height * ratio))), Image.Resampling.LANCZOS
            )
        buffer = io.BytesIO()
        # A fresh encode carries no EXIF / XMP / ICC from the upload.
        resized.save(buffer, format="WEBP", quality=WEBP_QUALITY, method=6)
        variants.append(
            EncodedVariant(resized.width, resized.height, buffer.getvalue())
        )
    return variants


def variant_key(asset_id: uuid.UUID, width: int) -> str:
    """Storage key of one variant."""
    return f"{MEDIA_PREFIX}/{asset_id}/{width}.webp"


def public_base_url(request_base_url: str | None = None) -> str:
    """Origin under which the API serves ``/media`` to browsers.

    ``MEDIA_PUBLIC_BASE_URL`` in production (the API's public origin, behind
    the reverse proxy); the request's own origin otherwise, which is right in
    development.
    """
    base = settings.MEDIA_PUBLIC_BASE_URL or request_base_url or "http://localhost:8000"
    return base.rstrip("/")


def variant_url(base_url: str, key: str) -> str:
    """Absolute URL of a stored variant."""
    return f"{base_url}{settings.API_V1_STR}/{key}"


_ASSET_ID_IN_URL = re.compile(
    r"/media/([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})/"
)


def asset_id_from_url(url: str | None) -> uuid.UUID | None:
    """The media asset an ``image_url`` points at, or None for an external
    URL (a category or product image typed by hand)."""
    if not url:
        return None
    match = _ASSET_ID_IN_URL.search(url)
    return uuid.UUID(match.group(1)) if match else None


async def alts_for_urls(
    session: Any, urls: Iterable[str | None]
) -> dict[str, str | None]:
    """``{image_url: alt}`` for the URLs that point at a media asset: what
    the storefront puts on ``<img alt>`` for a category tile, editable in the
    media library after the upload (03/10/2026)."""
    by_id: dict[uuid.UUID, list[str]] = {}
    for url in urls:
        asset_id = asset_id_from_url(url)
        if asset_id is not None and url:
            by_id.setdefault(asset_id, []).append(url)
    if not by_id:
        return {}
    rows = (
        await session.exec(
            select(MediaAsset.id, MediaAsset.alt).where(col(MediaAsset.id).in_(by_id))
        )
    ).all()
    alts: dict[str, str | None] = {}
    for asset_id, alt in rows:
        for url in by_id.get(asset_id, []):
            alts[url] = alt
    return alts


def to_public(asset: MediaAsset, base_url: str) -> MediaAssetPublic:
    """Describe an asset with its URLs and ``srcset``."""
    variants = sorted(asset.variants or [], key=lambda v: int(v["width"]))
    public_variants = [
        MediaVariantPublic(
            width=int(v["width"]),
            height=int(v["height"]),
            url=variant_url(base_url, str(v["key"])),
        )
        for v in variants
    ]
    largest = public_variants[-1] if public_variants else None
    return MediaAssetPublic(
        id=asset.id,
        kind=asset.kind,
        alt=asset.alt,
        original_filename=asset.original_filename,
        width=asset.width,
        height=asset.height,
        size_bytes=asset.size_bytes,
        url=largest.url if largest else "",
        srcset=", ".join(f"{v.url} {v.width}w" for v in public_variants),
        variants=public_variants,
    )


def validate_kind(kind: str) -> str:
    """Refuse an unknown kind rather than store a typo."""
    if kind not in MEDIA_KINDS:
        raise _invalid(
            f"Usage inconnu : {kind}. Valeurs possibles : {', '.join(MEDIA_KINDS)}.",
            "media.kind",
        )
    return kind


async def ingest_image(
    data: bytes,
    *,
    asset_id: uuid.UUID,
) -> tuple[list[dict[str, object]], int, int, int]:
    """Scan, re-encode and store an upload. Returns the variant rows, the
    largest width and height, and the total stored size."""
    if not data:
        raise _invalid("Fichier vide.")
    if len(data) > settings.MEDIA_MAX_UPLOAD_BYTES:
        limit_mb = settings.MEDIA_MAX_UPLOAD_BYTES // (1024 * 1024)
        raise AppError(
            code="media.too_large",
            status_code=413,
            message=f"Fichier trop lourd (maximum {limit_mb} Mo).",
        )

    scan = await get_antivirus_scanner().scan_bytes(data)
    if not scan.is_clean:
        raise AppError(
            code="media.infected",
            status_code=400,
            message="Le fichier a été refusé par l'antivirus.",
            details={"signature": scan.signature},
        )

    variants = await anyio.to_thread.run_sync(encode_variants, data)
    storage = get_file_storage()
    rows: list[dict[str, object]] = []
    stored: list[str] = []
    try:
        for variant in variants:
            key = variant_key(asset_id, variant.width)
            await storage.put_bytes(
                key=key, data=variant.data, content_type="image/webp"
            )
            stored.append(key)
            rows.append(
                {
                    "width": variant.width,
                    "height": variant.height,
                    "key": key,
                    "bytes": len(variant.data),
                }
            )
    except Exception:
        # Half-stored uploads leave no orphan files behind.
        for key in stored:
            try:
                await storage.delete(key=key)
            except Exception:  # noqa: BLE001 - best effort cleanup
                pass
        raise
    largest = variants[-1]
    return rows, largest.width, largest.height, sum(len(v.data) for v in variants)


async def delete_stored_variants(asset: MediaAsset) -> None:
    """Remove every stored variant of an asset (best effort per file)."""
    storage = get_file_storage()
    for variant in asset.variants or []:
        try:
            await storage.delete(key=str(variant["key"]))
        except Exception:  # noqa: BLE001 - a missing file is already gone
            continue
