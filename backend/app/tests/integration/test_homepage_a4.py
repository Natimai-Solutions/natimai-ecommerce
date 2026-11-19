"""Integration tests (real DB): the homepage preview and its SEO texts
(chantier accueil et messagerie, lot A4 / R10 and R11)."""

from __future__ import annotations

import datetime
import uuid
from typing import Any

import pytest
from fastapi import Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.homepage import (
    create_block,
    get_homepage,
    get_homepage_preview,
    homepage_preview_token,
    save_homepage_seo,
)
from app.core.datetimes import utcnow
from app.core.errors import AppError
from app.core.security import create_access_token, new_security_stamp
from app.features.content.models import HomepageBlockWrite, HomepageSeoWrite
from app.features.user.models.user import User
from app.tests.integration.test_media_and_homepage import _admin, _fresh, _request

pytestmark = pytest.mark.asyncio


async def _create(session: AsyncSession, admin: User, **fields: Any) -> uuid.UUID:
    created = await create_block(
        HomepageBlockWrite.model_validate(fields),
        _request(),
        session,
        await _fresh(session, admin),
    )
    return created.id


async def _preview(session: AsyncSession, token: str | None, **query: Any) -> Any:
    return await get_homepage_preview(
        _request(), Response(), session, x_homepage_preview=token, **query
    )


async def test_preview_shows_drafts_at_a_date_for_an_audience(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    in_a_week = utcnow() + datetime.timedelta(days=7)
    await _create(
        db_session,
        admin,
        kind="banner",
        title="Brouillon de Noël",
        is_published=False,
    )
    await _create(
        db_session,
        admin,
        kind="banner",
        title="Soldes",
        is_published=True,
        starts_at=in_a_week.isoformat(),
    )
    await _create(
        db_session,
        admin,
        kind="banner",
        title="Pour les clients",
        is_published=True,
        audience={"scope": "customer"},
    )
    await _create(
        db_session,
        admin,
        kind="announcement",
        title="Départ le 3/12",
        is_published=False,
    )

    def titles(page: Any) -> set[str]:
        return {s.title for s in page.sections}

    visitor = await get_homepage(_request(), db_session)
    assert titles(visitor) == set()
    link = await homepage_preview_token(await _fresh(db_session, admin))
    now = await _preview(db_session, link.token)
    assert titles(now) == {"Brouillon de Noël"}
    assert now.announcement is not None
    later = await _preview(
        db_session,
        link.token,
        at=in_a_week + datetime.timedelta(hours=1),
        scope="customer",
    )
    assert titles(later) == {"Brouillon de Noël", "Soldes", "Pour les clients"}
    # The preview leaves the visitor's page as it was.
    assert titles(await get_homepage(_request(), db_session)) == set()


async def test_preview_token_is_its_own_kind(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    link = await homepage_preview_token(await _fresh(db_session, admin))
    access = create_access_token(
        admin.id, datetime.timedelta(minutes=5), stamp=admin.security_stamp
    )
    for token in (None, "nonsense", access):
        with pytest.raises(AppError) as refused:
            await _preview(db_session, token)
        assert refused.value.code == "homepage.preview_invalid"
    # A changed security stamp (password, rights…) ends the link too.
    admin = await _fresh(db_session, admin)
    admin.security_stamp = new_security_stamp()
    db_session.add(admin)
    await db_session.commit()
    with pytest.raises(AppError):
        await _preview(db_session, link.token)


async def test_seo_texts_in_the_visitor_language(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    await save_homepage_seo(
        HomepageSeoWrite(
            title="Matériel informatique à Tahiti",
            description="Livré dans toutes les îles.",
            translations={"en": {"title": "Computer hardware in Tahiti"}},
        ),
        db_session,
        await _fresh(db_session, admin),
    )
    page = await get_homepage(_request(), db_session)
    assert page.seo is not None
    assert page.seo.title == "Matériel informatique à Tahiti"
    assert page.seo.translations == {}
