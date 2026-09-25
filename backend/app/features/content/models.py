"""Editable storefront pages (« Comment ça marche », CGV…).

A page is HTML written in the back-office editor and rendered by the
storefront after sanitising. A slug that matches a built-in legal page (``cgv``)
replaces its hard-coded content once published; ``comment-ca-marche`` is
seeded so the pre-order principle is explained from day one.
"""

# mypy: disable-error-code="assignment,misc,override"

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
