"""Integration tests (real DB): editable pages — admin upsert / delete, public
read of published pages only, idempotent seed."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.content_pages import (
    delete_page,
    get_public_page,
    list_pages,
    upsert_page,
)
from app.core.errors import AppError
from app.features.content.crud import crud_content_page, is_valid_slug
from app.features.content.models import ContentPageWrite
from app.features.initial_data import _seed_content_pages
from app.features.user.models.user import User


async def _admin(session: AsyncSession) -> User:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return cast(User, SimpleNamespace(id=admin.id))


def test_slug_rule() -> None:
    assert is_valid_slug("comment-ca-marche")
    assert is_valid_slug("cgv")
    for bad in ("", "Cgv", "a--b", "-a", "a b", "été", "a/b"):
        assert not is_valid_slug(bad), bad


@pytest.mark.asyncio
async def test_upsert_publish_and_public_read(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)

    with pytest.raises(AppError) as bad:
        await upsert_page("Not a slug", ContentPageWrite(title="x"), db_session, admin)
    assert bad.value.code == "content_page.slug.invalid"

    draft = await upsert_page(
        "cgv",
        ContentPageWrite(title="CGV", body_html="<p>v1</p>", is_published=False),
        db_session,
        admin,
    )
    assert draft.slug == "cgv" and not draft.is_published

    # A draft is invisible to the storefront…
    with pytest.raises(AppError) as hidden:
        await get_public_page("cgv", db_session)
    assert hidden.value.code == "content_page.not_found"

    # …until published; the upsert updates in place (same row, new content).
    published = await upsert_page(
        "cgv",
        ContentPageWrite(title="CGV", body_html="<p>v2</p>", is_published=True),
        db_session,
        admin,
    )
    assert published.id == draft.id
    public = await get_public_page("cgv", db_session)
    assert public.body_html == "<p>v2</p>"
    assert not hasattr(public, "created_by_id")

    assert [p.slug for p in await list_pages(db_session, admin)] == ["cgv"]

    removed = await delete_page("cgv", db_session, admin)
    assert removed.slug == "cgv"
    with pytest.raises(AppError):
        await get_public_page("cgv", db_session)
    with pytest.raises(AppError):
        await delete_page("cgv", db_session, admin)


@pytest.mark.asyncio
async def test_how_it_works_is_seeded_once_and_never_overwritten(
    db_session: AsyncSession,
) -> None:
    await _seed_content_pages(db_session)
    await db_session.commit()
    page = await crud_content_page.get_by_slug(db_session, "comment-ca-marche")
    assert page is not None and page.is_published
    assert "départ" in page.body_html

    page.body_html = "<p>Texte du propriétaire</p>"
    db_session.add(page)
    await db_session.commit()

    await _seed_content_pages(db_session)
    await db_session.commit()
    again = await crud_content_page.get_by_slug(db_session, "comment-ca-marche")
    assert again is not None and again.body_html == "<p>Texte du propriétaire</p>"


@pytest.mark.asyncio
async def test_legal_templates_are_listed_and_rendered_with_identity(
    db_session: AsyncSession,
) -> None:
    """R9 / T1: a legal page can be started from the built-in template, seller
    identity already substituted; what is still empty is a visible marker."""
    from app.api.routes.content_pages import get_page_template, list_page_templates
    from app.features.system.models.system_setting import SystemSetting

    admin = await _admin(db_session)

    templates = await list_page_templates(db_session, admin)
    assert [t.slug for t in templates] == ["cgv", "mentions-legales", "confidentialite"]
    assert not any(t.page_exists for t in templates)

    db_session.add(SystemSetting(key="legal_trading_name", value="Natimai & Co"))
    await db_session.flush()

    rendered = await get_page_template("mentions-legales", db_session, admin)
    assert rendered.title == "Mentions légales"
    assert "<strong>Natimai &amp; Co</strong>" in rendered.body_html
    assert "[À COMPLÉTER : n° TAHITI]" in rendered.body_html
    assert "{{" not in rendered.body_html

    with pytest.raises(AppError) as missing:
        await get_page_template("comment-ca-marche", db_session, admin)
    assert missing.value.code == "content_page.template.not_found"

    await upsert_page(
        "cgv", ContentPageWrite(title="CGV", body_html="<p>x</p>"), db_session, admin
    )
    templates = await list_page_templates(db_session, admin)
    assert {t.slug: t.page_exists for t in templates} == {
        "cgv": True,
        "mentions-legales": False,
        "confidentialite": False,
    }
