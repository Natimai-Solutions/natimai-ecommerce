"""Integration tests (real DB): the homepage sections of lot A3 (chantier
accueil et messagerie, R4 to R7) — the announcement above every page, the
reassurance band, the brand strip and the free content block."""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.homepage import (
    create_block,
    get_announcement,
    get_homepage,
    list_blocks,
)
from app.core.errors import AppError
from app.features.content.models import HomepageBlockWrite
from app.features.product.models.brand import Brand
from app.features.user.models.user import User
from app.tests.integration.test_media_and_homepage import _admin, _fresh, _request

pytestmark = pytest.mark.asyncio


async def _create(session: AsyncSession, admin: User, **fields: Any) -> uuid.UUID:
    created = await create_block(
        HomepageBlockWrite.model_validate({"is_published": True, **fields}),
        _request(),
        session,
        await _fresh(session, admin),
    )
    return created.id


async def _refused(session: AsyncSession, admin: User, **fields: Any) -> AppError:
    with pytest.raises(AppError) as refused:
        await _create(session, admin, **fields)
    return refused.value


async def test_one_announcement_for_everyone_outside_the_sections(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    await _create(
        db_session,
        admin,
        kind="announcement",
        title="Départ bateau le 3/12 : commandez avant le 28/11",
        cta_label="Voir",
        cta_link="/catalogue",
    )
    shown = await get_announcement(_request(), db_session)
    assert shown is not None and shown.title.startswith("Départ bateau")
    # Not a homepage section: it is above the header of every page.
    page = await get_homepage(_request(), db_session)
    assert all(s.kind != "announcement" for s in page.sections)

    second = await _refused(db_session, admin, kind="announcement", title="Soldes")
    assert second.code == "homepage.announcement.conflict"
    narrowed = await _refused(
        db_session,
        admin,
        kind="announcement",
        title="Clients",
        is_published=False,
        audience={"scope": "customer"},
    )
    assert narrowed.code == "homepage.audience"


async def test_reassurance_band_closed_icons_and_safe_links(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    items = [
        {
            "icon": "boat",
            "text": "Livraison dans les îles",
            "translations": {"en": "Island delivery"},
        },
        {"icon": "chat", "text": "Un conseiller vous répond", "link": "/contact"},
    ]
    await _create(db_session, admin, kind="reassurance", config={"items": items})
    page = await get_homepage(_request(), db_session)
    band = next(s for s in page.sections if s.kind == "reassurance")
    assert band.reassurance is not None
    assert [r.icon for r in band.reassurance] == ["boat", "chat"]
    assert band.reassurance[1].link == "/contact"

    for bad in (
        [{"icon": "skull", "text": "x"}, items[1]],
        [items[0], {"icon": "chat", "text": "x", "link": "/\\\\evil.example"}],
        [items[0], {"icon": "chat", "text": "x", "link": "javascript:alert(1)"}],
        [items[0]],
    ):
        refused = await _refused(
            db_session, admin, kind="reassurance", config={"items": bad}
        )
        assert refused.code == "homepage.config"
    # The same rule guards the call-to-action of every section.
    link = await _refused(
        db_session, admin, kind="banner", title="B", cta_link="/\\\\evil.example"
    )
    assert link.code == "homepage.link"


async def test_brand_strip_and_rich_text(db_session: AsyncSession) -> None:
    admin = await _admin(db_session)
    shown = Brand(name="Asus", slug="asus", image_url="https://cdn.example/asus.png")
    pending = Brand(
        name="Inconnue",
        slug="inconnue",
        image_url="https://cdn.example/x.png",
        is_validated=False,
    )
    db_session.add_all([shown, pending])
    ids = [shown.id, pending.id]
    await db_session.commit()

    await _create(
        db_session,
        admin,
        kind="brand_strip",
        config={"mode": "manual"},
        items=[{"brand_id": str(i)} for i in ids],
    )
    await _create(
        db_session,
        admin,
        kind="rich_text",
        body_html="<p>Notre boutique à <strong>Papeete</strong>.</p>",
        config={"image_side": "left"},
    )
    page = await get_homepage(_request(), db_session)
    strip = next(s for s in page.sections if s.kind == "brand_strip")
    # A brand still to validate never shows on the shop.
    assert strip.brands is not None and [b.slug for b in strip.brands] == ["asus"]
    text = next(s for s in page.sections if s.kind == "rich_text")
    assert text.body_html and "Papeete" in text.body_html

    admin_view = await list_blocks(
        _request(), db_session, await _fresh(db_session, admin)
    )
    listed = next(s for s in admin_view if s.kind == "brand_strip")
    assert [i.name for i in listed.items] == ["Asus", "Inconnue"]

    empty = await _refused(db_session, admin, kind="rich_text", body_html="  ")
    assert empty.code == "homepage.body"
