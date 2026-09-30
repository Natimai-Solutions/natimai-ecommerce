"""Editable pages: public read by slug, admin list / upsert."""

from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.content.crud import crud_content_page, is_valid_slug
from app.features.content.models import (
    SLUG_MAX_LENGTH,
    ContentPage,
    ContentPageCreate,
    ContentPagePublic,
    ContentPageSummary,
    ContentPageWrite,
)

router = APIRouter(tags=["content-pages"])


def _not_found(slug: str) -> AppError:
    return AppError(
        code="content_page.not_found",
        status_code=404,
        message="Page introuvable",
        details={"slug": slug},
    )


@router.get("/pages/{slug}", response_model=ContentPageSummary)
async def get_public_page(slug: str, session: SessionDep) -> ContentPageSummary:
    """A published page (no auth). The storefront sanitises the HTML."""
    page = await crud_content_page.get_by_slug(session, slug, published_only=True)
    if page is None:
        raise _not_found(slug)
    return ContentPageSummary.model_validate(page)


@router.get("/admin/pages", response_model=list[ContentPagePublic])
async def list_pages(
    session: SessionDep, _admin: CurrentSuperUser
) -> list[ContentPagePublic]:
    """Every page, published or not."""
    rows = (
        await session.exec(
            select(ContentPage)
            .where(col(ContentPage.is_active).is_(True))
            .order_by(col(ContentPage.slug).asc())
        )
    ).all()
    return [ContentPagePublic.model_validate(p) for p in rows]


@router.put("/admin/pages/{slug}", response_model=ContentPagePublic)
async def upsert_page(
    slug: str, body: ContentPageWrite, session: SessionDep, admin: CurrentSuperUser
) -> ContentPagePublic:
    """Create or replace a page by slug (title, body, publication)."""
    if len(slug) > SLUG_MAX_LENGTH or not is_valid_slug(slug):
        raise AppError(
            code="content_page.slug.invalid",
            status_code=400,
            message="Slug invalide : minuscules, chiffres et tirets (ex. comment-ca-marche)",
            details={"slug": slug},
        )
    existing = await crud_content_page.get_by_slug(session, slug)
    if existing is None:
        page = await crud_content_page.create(
            session,
            data=ContentPageCreate(slug=slug, **body.model_dump()),
            user=admin,
        )
    else:
        page = await crud_content_page.update(
            session, id=existing.id, data=body.model_dump(), user=admin, record=existing
        )
    return ContentPagePublic.model_validate(page)


@router.delete("/admin/pages/{slug}", response_model=ContentPageSummary)
async def delete_page(
    slug: str, session: SessionDep, admin: CurrentSuperUser
) -> ContentPageSummary:
    """Remove a page (a built-in legal page falls back to its default text)."""
    existing = await crud_content_page.get_by_slug(session, slug)
    if existing is None:
        raise _not_found(slug)
    summary = ContentPageSummary.model_validate(existing)
    await crud_content_page.delete(session, id=existing.id, record=existing, user=admin)
    return summary
