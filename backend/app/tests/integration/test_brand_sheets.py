"""Integration tests (real DB): brand sheets (chantier accueil et messagerie,
lot BR) — products linked from the supplier's manufacturer name, spellings
gathered by aliases and merges, the storefront showing validated sheets."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes import brand_pages
from app.core.errors import AppError
from app.features.product.crud.product import crud_product
from app.features.product.models.brand import Brand
from app.features.product.models.product import PricingMode, Product
from app.features.product.services import brands
from app.tasks.pricing_tasks import refresh_sale_prices

pytestmark = pytest.mark.asyncio


class _Request:
    class url:  # noqa: N801 - mimics starlette's request.url
        scheme = "http"
        netloc = "test"


def _product(name: str, manufacturer: str) -> Product:
    return Product(
        name=name,
        description="article de test",
        manufacturer=manufacturer,
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("10000"),
        supplier_name="tahiti",
        supplier_sku=f"sku-{uuid.uuid4().hex[:8]}",
        supplier_quantity=Decimal("5"),
        is_enriched=True,
    )


def test_brand_key() -> None:
    assert brands.brand_key("  HP Inc. ") == "hp"
    assert brands.brand_key("Hewlett-Packard Company") == "hewlett packard"
    assert brands.brand_key("Société Générale SA") == "societe generale"
    assert brands.brand_key("Inc") == "inc"
    assert brands.slugify("TP-Link") == "tp-link"


async def _brand_of(session: AsyncSession, product_id: uuid.UUID) -> Brand | None:
    product = await session.get(Product, product_id)
    assert product is not None
    await session.refresh(product)
    return await session.get(Brand, product.brand_id) if product.brand_id else None


async def test_spellings_link_merge_and_search(db_session: AsyncSession) -> None:
    rows = [
        _product("Portable", "HP"),
        _product("Imprimante", "HP Inc."),
        _product("Écran", "Hewlett-Packard"),
        _product("Souris", "Logitech"),
    ]
    db_session.add_all(rows)
    ids = [p.id for p in rows]
    await db_session.commit()
    await refresh_sale_prices(db_session)

    await brands.link_unbranded_products(db_session)
    hp = await _brand_of(db_session, ids[0])
    assert hp is not None and not hp.is_validated
    hp_id = hp.id
    # « HP Inc. » is the same key as « HP »; « Hewlett-Packard » is not.
    assert (b := await _brand_of(db_session, ids[1])) and b.id == hp_id
    hewlett = await _brand_of(db_session, ids[2])
    assert hewlett is not None and hewlett.id != hp_id
    hewlett_id = hewlett.id

    # The admin merges the long name into HP and validates the sheet.
    merged = await brand_pages.admin_merge_brand(
        hewlett_id,
        brand_pages.BrandMerge(target_id=hp_id),
        _Request(),  # type: ignore[arg-type]
        db_session,
        None,  # type: ignore[arg-type]
    )
    assert merged.product_count == 3
    assert merged.aliases == ["Hewlett-Packard"]
    saved = await brand_pages.admin_update_brand(
        hp_id,
        brand_pages.BrandWrite(
            name="HP", aliases=["Hewlett-Packard", "HPE"], is_validated=True
        ),
        _Request(),  # type: ignore[arg-type]
        db_session,
        None,  # type: ignore[arg-type]
    )
    assert saved.slug == "hp" and saved.is_validated

    # A new import under the alias lands on HP.
    db_session.add(late := _product("Station", "HPE"))
    late_id = late.id
    await db_session.commit()
    await brands.link_unbranded_products(db_session)
    assert (b := await _brand_of(db_session, late_id)) and b.id == hp_id

    # Facets name the validated brand once; a sheet to validate shows as given.
    result: dict[str, Any] = await crud_product.search_products(
        db_session, group_offers=False
    )
    makers = result["facets"]["manufacturers"]
    assert makers.get("HP") == 4
    assert makers.get("Logitech") == 1
    # Filtering by the facet name finds every spelling.
    found = await crud_product.search_products(
        db_session, manufacturer="HP", group_offers=False, with_facets=False
    )
    assert {p.name for p in found["data"]} == {
        "Portable",
        "Imprimante",
        "Écran",
        "Station",
    }
    by_page = await crud_product.search_products(
        db_session, brand_id=hp_id, group_offers=False, with_facets=False
    )
    assert by_page["count"] == 4

    # The storefront page: validated sheets only.
    page = await brand_pages.get_brand_page(
        "hp",
        _Request(),  # type: ignore[arg-type]
        db_session,
    )
    assert page.name == "HP"
    logitech = (
        await db_session.exec(select(Brand).where(col(Brand.name) == "Logitech"))
    ).one()
    with pytest.raises(AppError) as hidden:
        await brand_pages.get_brand_page(
            logitech.slug or "",
            _Request(),  # type: ignore[arg-type]
            db_session,
        )
    assert hidden.value.status_code == 404


async def test_slug_and_name_are_unique(db_session: AsyncSession) -> None:
    created = await brand_pages.admin_create_brand(
        brand_pages.BrandWrite(name="Dell"),
        _Request(),  # type: ignore[arg-type]
        db_session,
        None,  # type: ignore[arg-type]
    )
    assert created.slug == "dell"
    for body, code in (
        (brand_pages.BrandWrite(name="DELL Inc."), "brand.slug_taken"),
        (brand_pages.BrandWrite(name="Dell", slug="dell-2"), "brand.exists"),
    ):
        with pytest.raises(AppError) as refused:
            await brand_pages.admin_create_brand(
                body,
                _Request(),  # type: ignore[arg-type]
                db_session,
                None,  # type: ignore[arg-type]
            )
        assert refused.value.code == code


async def test_hiding_renaming_and_merging_keep_the_products(
    db_session: AsyncSession,
) -> None:
    """A hidden sheet keeps its products (the hourly pass made a duplicate
    « to validate »); a renamed one keeps its former name as an alias (its
    products went back to a new sheet); renaming onto another sheet's name
    is refused; a merge moves the homepage tiles."""
    from app.features.content.models import HomepageBlock, HomepageBlockItem

    acer, hewlett, hp = (
        _product("Portable", "Acer"),
        _product("Écran", "Hewlett-Packard"),
        _product("Souris", "HP"),
    )
    db_session.add_all([acer, hewlett, hp])
    ids = {"acer": acer.id, "hewlett": hewlett.id, "hp": hp.id}
    await db_session.commit()
    await brands.link_unbranded_products(db_session)

    async def brand_of(key: str) -> Brand:
        found = await _brand_of(db_session, ids[key])
        assert found is not None
        return found

    acer_brand = await brand_of("acer")
    acer_id = acer_brand.id
    await brand_pages.admin_update_brand(
        acer_id,
        brand_pages.BrandWrite(name="Acer", is_active=False),
        _Request(),  # type: ignore[arg-type]
        db_session,
        None,  # type: ignore[arg-type]
    )
    await brands.link_unbranded_products(db_session)
    assert (await brand_of("acer")).id == acer_id
    assert (
        await db_session.exec(select(Brand).where(col(Brand.name) == "Acer"))
    ).all().__len__() == 1

    hewlett_id = (await brand_of("hewlett")).id
    hp_id = (await brand_of("hp")).id
    with pytest.raises(AppError) as taken:
        await brand_pages.admin_update_brand(
            hewlett_id,
            brand_pages.BrandWrite(name="HP Inc."),
            _Request(),  # type: ignore[arg-type]
            db_session,
            None,  # type: ignore[arg-type]
        )
    assert taken.value.code == "brand.exists"

    renamed = await brand_pages.admin_update_brand(
        hewlett_id,
        brand_pages.BrandWrite(name="HPE", slug="hpe"),
        _Request(),  # type: ignore[arg-type]
        db_session,
        None,  # type: ignore[arg-type]
    )
    assert renamed.aliases == ["Hewlett-Packard"]
    await brands.link_unbranded_products(db_session)
    assert (await brand_of("hewlett")).id == hewlett_id

    strip = HomepageBlock(kind="brand_strip", config={"mode": "manual"})
    db_session.add(strip)
    await db_session.flush()
    db_session.add(HomepageBlockItem(block_id=strip.id, brand_id=hewlett_id))
    strip_id = strip.id
    await db_session.commit()
    await brand_pages.admin_merge_brand(
        hewlett_id,
        brand_pages.BrandMerge(target_id=hp_id),
        _Request(),  # type: ignore[arg-type]
        db_session,
        None,  # type: ignore[arg-type]
    )
    tiles = (
        await db_session.exec(
            select(HomepageBlockItem).where(col(HomepageBlockItem.block_id) == strip_id)
        )
    ).all()
    assert [t.brand_id for t in tiles] == [hp_id]


async def test_the_brand_filter_is_exact_for_a_sheet_and_literal_otherwise(
    db_session: AsyncSession,
) -> None:
    rows = [
        _product("A", "HP"),
        _product("B", "HPE"),
        _product("C", "3_M"),
        _product("D", "3XM"),
    ]
    db_session.add_all(rows)
    await db_session.commit()
    await refresh_sale_prices(db_session)
    await brands.link_unbranded_products(db_session)
    hp = (await db_session.exec(select(Brand).where(col(Brand.name) == "HP"))).one()
    hp.is_validated = True
    db_session.add(hp)
    await db_session.commit()

    async def names(manufacturer: str) -> set[str]:
        found = await crud_product.search_products(
            db_session, manufacturer=manufacturer, group_offers=False, with_facets=False
        )
        return {p.name for p in found["data"]}

    assert await names("HP") == {"A"}
    assert await names("3_M") == {"C"}


async def test_a_sheet_saved_under_its_own_name_beside_a_hidden_namesake(
    db_session: AsyncSession,
) -> None:
    hidden = Brand(name="Acer", slug="acer", is_active=False)
    shown = Brand(name="ACER", slug="acer-2")
    db_session.add_all([hidden, shown])
    ids = (hidden.id, shown.id)
    await db_session.commit()
    for brand_id, slug in zip(ids, ("acer", "acer-2"), strict=True):
        saved = await brand_pages.admin_update_brand(
            brand_id,
            brand_pages.BrandWrite(name="Acer", slug=slug, description="Portables"),
            _Request(),  # type: ignore[arg-type]
            db_session,
            None,  # type: ignore[arg-type]
        )
        assert saved.description == "Portables"


async def test_brand_page_language_sitemap_and_product_link(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    from app.api.routes import product as product_routes

    hp = Brand(
        name="HP",
        slug="hp",
        description="Ordinateurs et imprimantes.",
        translations={"en": {"description": "Computers and printers."}},
    )
    hidden = Brand(name="Acer", slug="acer", is_active=False)
    db_session.add_all([hp, hidden])
    await db_session.flush()
    laptop = _product("Portable", "HP")
    laptop.brand_id = hp.id
    other = _product("Écran", "Acer")
    other.brand_id = hidden.id
    db_session.add_all([laptop, other])
    ids = (laptop.id, other.id)
    await db_session.commit()

    monkeypatch.setattr(brand_pages, "request_locale", lambda: "en")
    page = await brand_pages.get_brand_page("hp", _Request(), db_session)  # type: ignore[arg-type]
    assert page.description == "Computers and printers."
    # Only validated, shown brands with products go to the sitemap.
    assert [e.slug for e in await brand_pages.brand_sitemap(db_session)] == ["hp"]

    read = product_routes.router.generate_read_endpoint()
    shown = await read(db_session, ids[0], None)
    assert (shown.brand_name, shown.brand_slug) == ("HP", "hp")
    hidden_brand = await read(db_session, ids[1], None)
    assert hidden_brand.brand_slug is None


async def test_a_brand_selection_follows_a_merge_and_blocks_a_delete(
    db_session: AsyncSession,
) -> None:
    """Review of PR 204: a homepage selection « products of a brand » kept
    the id of a merged (or deleted) sheet and emptied itself without a word."""
    from app.features.content.models import HomepageBlock

    source = Brand(name="Lenovo Group", slug="lenovo-group")
    target = Brand(name="Lenovo", slug="lenovo")
    db_session.add_all([source, target])
    source_id, target_id = source.id, target.id
    block = HomepageBlock(
        kind="collection",
        title="Lenovo",
        config={"source": "brand", "brand_id": str(source_id), "limit": 8},
    )
    db_session.add(block)
    block_id = block.id
    await db_session.commit()

    with pytest.raises(AppError) as used:
        await brand_pages.admin_delete_brand(source_id, db_session, None)  # type: ignore[arg-type]
    assert used.value.code == "brand.in_use" and used.value.status_code == 409

    await brand_pages.admin_merge_brand(
        source_id,
        brand_pages.BrandMerge(target_id=target_id),
        _Request(),  # type: ignore[arg-type]
        db_session,
        None,  # type: ignore[arg-type]
    )
    row = await db_session.get(HomepageBlock, block_id)
    assert row is not None
    await db_session.refresh(row)
    assert row.config == {"source": "brand", "brand_id": str(target_id), "limit": 8}
