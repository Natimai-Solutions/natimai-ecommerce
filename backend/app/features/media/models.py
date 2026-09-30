"""Public media assets: images uploaded from the back-office.

An upload is re-encoded into a few WebP widths (``variants``); each variant is
served at ``GET /media/{asset_id}/{width}.webp``. The original file is never
kept: it may carry EXIF data (GPS position, camera serial) and an arbitrary
format, and nothing needs it once the variants exist.
"""

# mypy: disable-error-code="assignment,misc,override"

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.features.base.models import Base

#: What the image is for; drives the picker's filter in the admin.
MEDIA_KINDS: tuple[str, ...] = ("homepage", "product", "category", "page", "other")


class MediaAssetBase(Base):
    """Fields shared by the table and its schemas."""

    kind: str = Field(default="other", max_length=30, index=True)
    original_filename: str | None = Field(default=None, max_length=255)
    alt: str | None = Field(
        default=None, max_length=255, description="Alternative text (accessibility)"
    )
    width: int = Field(ge=1, description="Width of the largest variant, in pixels")
    height: int = Field(ge=1, description="Height of the largest variant, in pixels")
    size_bytes: int = Field(ge=0, description="Total size of the stored variants")
    variants: list[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
        description="[{width, height, key, bytes}] sorted by width, WebP",
    )


class MediaAsset(MediaAssetBase, table=True):
    """Represents a media asset."""

    __tablename__ = "media_assets"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class MediaVariantPublic(SQLModel):
    """One served size of an image."""

    width: int
    height: int
    url: str


class MediaAssetPublic(SQLModel):
    """What the admin and the storefront need to show an image."""

    id: uuid.UUID
    kind: str
    alt: str | None = None
    original_filename: str | None = None
    width: int
    height: int
    size_bytes: int
    #: URL of the largest variant (the one to store in an ``image_url`` field).
    url: str
    #: ``srcset`` attribute value: every variant with its width descriptor.
    srcset: str
    variants: list[MediaVariantPublic] = []


class MediaAssetUpdate(SQLModel):
    """Admin edit: the alternative text and the kind."""

    alt: str | None = Field(default=None, max_length=255)
    kind: str | None = Field(default=None, max_length=30)
