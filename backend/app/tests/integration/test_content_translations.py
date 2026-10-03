"""Translated content on the public API (R9 / T3): products, categories,
pages, homepage blocks and spec labels follow the request's language; the
back-office keeps the source language and stamps what it saves."""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from datetime import UTC
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from fastapi import Request
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_categories import AdminCategoryUpdate, update_category
from app.api.routes.admin_product import admin_create_product, admin_update_product
from app.api.routes.content_pages import get_public_page, upsert_page
from app.api.routes.homepage import create_block, get_homepage
from app.api.routes.product_catalog import search_products
from app.core import i18n
from app.core.errors import AppError
from app.features.content.models import ContentPageWrite, HomepageBlockWrite
from app.features.product.models.category import Category
from app.features.product.models.product import (
    PricingMode,
    ProductCreate,
    ProductSearchRequest,
    ProductUpdate,
)
from app.features.user.models.user import User


@pytest.fixture
def english() -> Iterator[None]:
    """The request speaks English (``Accept-Language: en``)."""
    token = i18n.set_request_locale("en")
    try:
        yield
    finally:
        i18n.reset_request_locale(token)


async def _admin(session: AsyncSession) -> User:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return cast(
        User, SimpleNamespace(id=admin.id, email=admin.email, is_superuser=True)
    )


def _request() -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(b"host", b"testserver")],
            "scheme": "http",
            "server": ("testserver", 80),
        }
    )


@pytest.mark.asyncio
@pytest.mark.usefixtures("english")
async def test_products_are_served_in_the_visitor_language_and_stay_source_for_admins(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    created = await admin_create_product(
        db_session,
        admin,
        ProductCreate(
            name="Souris sans fil",
            description="Souris Bluetooth",
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("5000"),
            supplier_quantity=Decimal("3"),
            is_enriched=True,
            translations={"en": {"name": "Wireless mouse", "description": "  "}},
        ),
    )
    # The back-office answer is the source language, with the stamped mapping.
    assert created.name == "Souris sans fil"
    assert created.translations["en"]["name"] == "Wireless mouse"
    assert "description" not in created.translations["en"]
    assert "_source" in created.translations["en"]
    assert created.translation_status == {"en": "ok"}

    # A visitor searching in English reads the translation, falls back on the
    # source for the untranslated field, and finds the product by its English
    # name (the index covers it).
    found = await search_products(db_session, ProductSearchRequest(q="wireless"), None)
    assert [p.name for p in found.data] == ["Wireless mouse"]
    assert found.data[0].description == "Souris Bluetooth"
    assert found.data[0].model_dump().get("translations") is None  # redacted

    # Editing the French name makes the translation stale; a save that only
    # resends the same English text keeps it stale; new text refreshes it.
    updated = await admin_update_product(
        db_session, admin, created.id, ProductUpdate(name="Souris sans fil pro")
    )
    assert updated.translation_status == {"en": "stale"}
    resent = await admin_update_product(
        db_session,
        admin,
        created.id,
        ProductUpdate(translations={"en": {"name": "Wireless mouse"}}),
    )
    assert resent.translation_status == {"en": "stale"}
    fixed = await admin_update_product(
        db_session,
        admin,
        created.id,
        ProductUpdate(translations={"en": {"name": "Wireless mouse pro"}}),
    )
    assert fixed.translation_status == {"en": "ok"}
    assert "translations" not in (fixed.overridden_fields or [])

    with pytest.raises(AppError) as refused:
        await admin_update_product(
            db_session,
            admin,
            created.id,
            ProductUpdate(translations={"es": {"name": "Ratón"}}),
        )
    assert refused.value.code == "product.translations.invalid"


@pytest.mark.asyncio
@pytest.mark.usefixtures("english")
async def test_categories_pages_blocks_and_spec_labels_follow_the_language(
    db_session: AsyncSession,
) -> None:
    from app.api.routes.category import router as category_router
    from app.features.product.services.spec_projection import (
        get_effective_spec_definitions,
    )

    admin = await _admin(db_session)

    # Category: translated display_name drives the storefront title.
    category = Category(name="Portables", display_name="Ordinateurs portables")
    db_session.add(category)
    await db_session.flush()
    item = await update_category(
        category.id,
        AdminCategoryUpdate(translations={"en": {"display_name": "Laptops"}}),
        db_session,
        admin,
    )
    assert item.title == "Ordinateurs portables"
    assert item.translation_status == {"en": "ok"}
    read_multi = category_router.generate_read_multi_endpoint()
    visitor_view = await read_multi(db_session, current_user=None)
    titles = {c.id: c.title for c in visitor_view.data}
    assert titles[category.id] == "Laptops"
    admin_view = await read_multi(db_session, current_user=admin)
    assert {c.id: c.title for c in admin_view.data}[
        category.id
    ] == "Ordinateurs portables"

    # Page: the English version when there is one, ``lang`` says which.
    await upsert_page(
        "livraison",
        ContentPageWrite(
            title="Livraison",
            body_html="<p>FR</p>",
            is_published=True,
            translations={"en": {"title": "Delivery", "body_html": "<p>EN</p>"}},
        ),
        db_session,
        admin,
    )
    page = await get_public_page("livraison", db_session)
    assert (page.title, page.body_html, page.lang) == ("Delivery", "<p>EN</p>", "en")
    await upsert_page(
        "retours",
        ContentPageWrite(title="Retours", body_html="<p>FR</p>", is_published=True),
        db_session,
        admin,
    )
    untranslated = await get_public_page("retours", db_session)
    assert (untranslated.title, untranslated.lang) == ("Retours", "fr")

    # Homepage block: translated title on the storefront, source in the admin.
    block = await create_block(
        HomepageBlockWrite(
            kind="hero",
            title="Bienvenue",
            subtitle="Matériel importé",
            is_published=True,
            translations={"en": {"title": "Welcome"}},
        ),
        _request(),
        db_session,
        admin,
    )
    assert block.title == "Bienvenue" and block.translation_status == {"en": "ok"}
    home = await get_homepage(_request(), db_session)
    assert home.hero is not None
    assert (home.hero.title, home.hero.subtitle) == ("Welcome", "Matériel importé")

    # Spec labels: the storefront facets read the translated label.
    from datetime import datetime

    from app.features.product.models.spec_definition import SpecDefinition

    db_session.add(
        SpecDefinition(
            key="memory_gb",
            label_fr="Mémoire (Go)",
            type="numeric",
            unit="Go",
            translations={"en": {"label_fr": "Memory (GB)", "_source": "x"}},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
    )
    await db_session.commit()
    labels = {
        d["key"]: d["label_fr"]
        for d in await get_effective_spec_definitions(db_session)
    }
    assert labels["memory_gb"] == "Memory (GB)"
