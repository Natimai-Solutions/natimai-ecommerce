"""CRUD for content pages."""

from __future__ import annotations

import re

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.base.crud import CrudBase
from app.features.content.models import (
    ContentPage,
    ContentPageCreate,
    ContentPageUpdate,
)

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def is_valid_slug(slug: str) -> bool:
    """Lower-case words joined by single dashes: ``comment-ca-marche``."""
    return bool(_SLUG_RE.match(slug))


class ContentPageCrud(CrudBase[ContentPage, ContentPageCreate, ContentPageUpdate]):
    """Represents content page crud."""

    async def get_by_slug(
        self, session: AsyncSession, slug: str, *, published_only: bool = False
    ) -> ContentPage | None:
        """Get by slug."""
        statement = select(ContentPage).where(
            col(ContentPage.slug) == slug, col(ContentPage.is_active).is_(True)
        )
        if published_only:
            statement = statement.where(col(ContentPage.is_published).is_(True))
        return (await session.exec(statement)).first()


crud_content_page = ContentPageCrud(
    model=ContentPage,
    schema_create=ContentPageCreate,
    schema_update=ContentPageUpdate,
    order_by=col(ContentPage.slug).asc(),
)
