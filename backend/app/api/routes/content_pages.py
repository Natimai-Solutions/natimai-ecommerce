"""Editable pages: public read by slug, admin list / upsert."""

from __future__ import annotations

from fastapi import APIRouter
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.content_i18n import (
    CONTENT_PAGE_FIELDS,
    InvalidTranslations,
    clean_translations,
    translated_values,
)
from app.core.errors import AppError
from app.core.i18n import default_locale, request_locale
from app.features.content.crud import crud_content_page, is_valid_slug
from app.features.content.legal_templates import (
    LEGAL_TEMPLATES,
    get_template,
    render_legal_template_from_db,
)
from app.features.content.models import (
    SLUG_MAX_LENGTH,
    ContentPage,
    ContentPageCreate,
    ContentPagePublic,
    ContentPageSummary,
    ContentPageTemplate,
    ContentPageTemplateSummary,
    ContentPageWrite,
)

router = APIRouter(tags=["content-pages"])


def _bad_translations(exc: InvalidTranslations) -> AppError:
    return AppError(
        code="content.translations.invalid",
        status_code=400,
        message=f"Traductions invalides : {exc}",
    )


def _not_found(slug: str) -> AppError:
    return AppError(
        code="content_page.not_found",
        status_code=404,
        message="Page introuvable",
        details={"slug": slug},
    )


@router.get("/pages/{slug}", response_model=ContentPageSummary)
async def get_public_page(slug: str, session: SessionDep) -> ContentPageSummary:
    """A published page (no auth), in the request's language when translated
    (R9 / T3), else in the shop's default language (``lang`` says which). The
    storefront sanitises the HTML."""
    page = await crud_content_page.get_by_slug(session, slug, published_only=True)
    if page is None:
        raise _not_found(slug)
    lang = request_locale()
    texts = translated_values(page.translations, CONTENT_PAGE_FIELDS, lang)
    return ContentPageSummary(
        slug=page.slug,
        title=texts.get("title") or page.title,
        body_html=texts.get("body_html") or page.body_html,
        lang=lang if texts else default_locale(),
    )


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


@router.get("/admin/pages/templates", response_model=list[ContentPageTemplateSummary])
async def list_page_templates(
    session: SessionDep, _admin: CurrentSuperUser
) -> list[ContentPageTemplateSummary]:
    """The built-in legal pages a page can be started from (R9 / T1)."""
    existing = set(
        (
            await session.exec(
                select(ContentPage.slug).where(col(ContentPage.is_active).is_(True))
            )
        ).all()
    )
    return [
        ContentPageTemplateSummary(
            slug=t.slug, title=t.title, page_exists=t.slug in existing
        )
        for t in LEGAL_TEMPLATES
    ]


@router.get("/admin/pages/templates/{slug}", response_model=ContentPageTemplate)
async def get_page_template(
    slug: str, session: SessionDep, _admin: CurrentSuperUser
) -> ContentPageTemplate:
    """The template text with the seller identity substituted, ready to edit."""
    template = get_template(slug)
    if template is None:
        raise AppError(
            code="content_page.template.not_found",
            status_code=404,
            message="Aucun modèle pour cette page",
            details={"slug": slug},
        )
    body_html = await render_legal_template_from_db(session, slug)
    return ContentPageTemplate(slug=slug, title=template.title, body_html=body_html)


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
    data = body.model_dump()
    try:
        data["translations"] = clean_translations(
            body.translations,
            previous=existing.translations if existing is not None else None,
            source_values=data,
            fields=CONTENT_PAGE_FIELDS,
        )
    except InvalidTranslations as exc:
        raise _bad_translations(exc)
    if existing is None:
        page = await crud_content_page.create(
            session, data=ContentPageCreate(slug=slug, **data), user=admin
        )
    else:
        page = await crud_content_page.update(
            session, id=existing.id, data=data, user=admin, record=existing
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
