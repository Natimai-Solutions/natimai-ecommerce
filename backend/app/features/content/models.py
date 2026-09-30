"""Editable storefront pages (« Comment ça marche », CGV…).

A page is HTML written in the back-office editor and rendered by the
storefront after sanitising. A slug that matches a built-in legal page (``cgv``)
replaces its hard-coded content once published; ``comment-ca-marche`` is
seeded so the pre-order principle is explained from day one.
"""

# mypy: disable-error-code="assignment,misc,override"

import datetime
import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate

SLUG_MAX_LENGTH = 80


class ContentPageBase(Base):
    """Fields shared by the table and its schemas."""

    slug: str = Field(
        max_length=SLUG_MAX_LENGTH,
        index=True,
        unique=True,
        description="URL key, e.g. comment-ca-marche",
    )
    title: str = Field(max_length=200)
    body_html: str = Field(default="", description="HTML from the admin editor")
    is_published: bool = Field(default=False, index=True)


class ContentPage(ContentPageBase, table=True):
    """Represents a content page."""

    __tablename__ = "content_pages"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class ContentPageCreate(ContentPageBase, BaseCreate):
    """Represents content page create."""

    pass


class ContentPageUpdate(BaseUpdate):
    """Represents content page update."""

    title: str | None = None
    body_html: str | None = None
    is_published: bool | None = None


class ContentPageWrite(SQLModel):
    """Admin upsert payload (the slug is in the URL)."""

    title: str = Field(max_length=200)
    body_html: str = ""
    is_published: bool = False


class ContentPagePublic(ContentPageBase, BasePublic):
    """Admin view."""

    id: uuid.UUID


class ContentPageSummary(SQLModel):
    """Storefront view: what the page shows, nothing more."""

    slug: str
    title: str
    body_html: str


# --------------------------------------------------------------------------
# Homepage blocks (R2): the hero and the banners of the storefront homepage.
# --------------------------------------------------------------------------
HOMEPAGE_BLOCK_KINDS: tuple[str, ...] = ("hero", "banner")


class HomepageBlockBase(Base):
    """Fields shared by the table and its schemas."""

    kind: str = Field(default="banner", max_length=20, index=True)
    title: str = Field(max_length=200)
    subtitle: str | None = Field(default=None, max_length=500)
    cta_label: str | None = Field(default=None, max_length=60)
    cta_link: str | None = Field(
        default=None,
        max_length=500,
        description="Storefront path (/catalogue?cat=…) or absolute https URL",
    )
    media_id: uuid.UUID | None = Field(
        default=None, foreign_key="media_assets.id", index=True, ondelete="SET NULL"
    )
    image_url: str | None = Field(
        default=None, max_length=500, description="External image, when no media is set"
    )
    alt: str | None = Field(default=None, max_length=255)
    position: int = Field(default=0, index=True)
    is_published: bool = Field(default=False, index=True)
    starts_at: datetime.datetime | None = Field(default=None)
    ends_at: datetime.datetime | None = Field(default=None)


class HomepageBlock(HomepageBlockBase, table=True):
    """Represents a homepage block."""

    __tablename__ = "homepage_blocks"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class HomepageBlockWrite(SQLModel):
    """Admin create / replace payload."""

    kind: str = Field(default="banner", max_length=20)
    title: str = Field(min_length=1, max_length=200)
    subtitle: str | None = Field(default=None, max_length=500)
    cta_label: str | None = Field(default=None, max_length=60)
    cta_link: str | None = Field(default=None, max_length=500)
    media_id: uuid.UUID | None = None
    image_url: str | None = Field(default=None, max_length=500)
    alt: str | None = Field(default=None, max_length=255)
    position: int = 0
    is_published: bool = False
    starts_at: datetime.datetime | None = None
    ends_at: datetime.datetime | None = None


class HomepageImage(SQLModel):
    """An image ready for an ``<img>``: source, srcset and intrinsic size."""

    src: str
    srcset: str | None = None
    width: int | None = None
    height: int | None = None
    alt: str = ""


class HomepageBlockPublic(SQLModel):
    """A block as the storefront and the admin see it."""

    id: uuid.UUID
    kind: str
    title: str
    subtitle: str | None = None
    cta_label: str | None = None
    cta_link: str | None = None
    media_id: uuid.UUID | None = None
    image_url: str | None = None
    alt: str | None = None
    position: int = 0
    is_published: bool = False
    starts_at: datetime.datetime | None = None
    ends_at: datetime.datetime | None = None
    image: HomepageImage | None = None


class HomepagePublic(SQLModel):
    """Storefront homepage content: at most one hero, then the banners."""

    hero: HomepageBlockPublic | None = None
    banners: list[HomepageBlockPublic] = []
