"""Integration tests (real DB): the homepage sections (chantier accueil et
messagerie, R1 and R8) — ordered, hidden, titled, shown to an audience, and
the products of a product section priced for whoever looks."""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any

import pytest
from fastapi import Response
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.homepage import (
    create_block,
    get_homepage,
    get_personal_homepage,
    list_blocks,
    reorder_blocks,
    replace_block,
)
from app.core.errors import AppError
from app.features.content.models import HomepageBlockWrite, HomepageOrder
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import PricingMode, Product
from app.features.user.models.user import User
from app.tests.integration.test_media_and_homepage import _admin, _fresh, _request

pytestmark = pytest.mark.asyncio


async def _shop(session: AsyncSession) -> dict[str, Any]:
    """A default group, a « Professionnels » group at −10 %, two featured
    products, a visitor-priced customer and a pro customer."""
    particulier = PriceGroup(code="particulier", label="Particulier", default=True)
    pro = PriceGroup(code="pro", label="Professionnels", discount_pct=Decimal("10"))
    session.add_all([particulier, pro])
    await session.flush()
    for name, price in (("Écran 27", "45000"), ("Clavier", "5000")):
        session.add(
            Product(
                name=name,
                pricing_mode=PricingMode.FIXED,
                base_price=Decimal(price),
                is_featured=True,
                is_enriched=True,
                weight=1.0,
                customs_rate_pct=Decimal("0"),
            )
        )
    customers = {}
    for key, group in (("particulier", None), ("pro", pro)):
        user = User(
            email=f"{key}+{uuid.uuid4().hex[:6]}@t.local",
            hashed_password="x",
            is_active=True,
            is_verified=True,
            price_group_id=group.id if group else None,
        )
        session.add(user)
        await session.flush()
        customers[key] = user.id
    pro_group = pro.id
    await session.commit()
    return {"pro_group": pro_group, "customers": customers}


async def _section(session: AsyncSession, admin: User, **fields: object) -> uuid.UUID:
    created = await create_block(
        HomepageBlockWrite.model_validate({"is_published": True, **fields}),
        _request(),
        session,
        await _fresh(session, admin),
    )
    return created.id


async def _page_of(session: AsyncSession, user_id: uuid.UUID | None) -> list[Any]:
    if user_id is None:
        return (await get_homepage(_request(), session)).sections
    user = await session.get(User, user_id)
    assert user is not None
    await session.refresh(user)
    return (await get_personal_homepage(_request(), Response(), session, user)).sections


async def test_each_audience_sees_its_sections_and_its_prices(
    db_session: AsyncSession,
) -> None:
    shop = await _shop(db_session)
    admin = await _admin(db_session)
    await _section(
        db_session,
        admin,
        kind="hero",
        title="Noël : −15 % sur les écrans",
        audience={"scope": "guest"},
    )
    await _section(
        db_session,
        admin,
        kind="hero",
        title="Équipez vos bureaux",
        audience={"scope": "customer", "price_group_ids": [str(shop["pro_group"])]},
    )
    await _section(db_session, admin, kind="featured", title="Nos coups de cœur")
    await _section(
        db_session,
        admin,
        kind="banner",
        title="Cartes cadeaux",
        audience={"scope": "guest"},
    )
    await _section(
        db_session,
        admin,
        kind="banner",
        title="Paiement à 30 jours",
        audience={"scope": "customer", "price_group_ids": [str(shop["pro_group"])]},
    )
    await _section(
        db_session,
        admin,
        kind="banner",
        title="Pour nos clients",
        audience={"scope": "customer"},
    )

    def titles(sections: list[Any]) -> list[str]:
        return [s.title for s in sections]

    def prices(sections: list[Any]) -> dict[str, Decimal]:
        featured = next(s for s in sections if s.kind == "featured")
        return {p.name: p.base_price for p in featured.products}

    visitor = await _page_of(db_session, None)
    assert titles(visitor) == [
        "Noël : −15 % sur les écrans",
        "Nos coups de cœur",
        "Cartes cadeaux",
    ]
    assert prices(visitor) == {"Écran 27": Decimal("45000"), "Clavier": Decimal("5000")}

    particulier = await _page_of(db_session, shop["customers"]["particulier"])
    assert titles(particulier) == ["Nos coups de cœur", "Pour nos clients"]
    assert prices(particulier) == prices(visitor)

    pro = await _page_of(db_session, shop["customers"]["pro"])
    assert titles(pro) == [
        "Équipez vos bureaux",
        "Nos coups de cœur",
        "Paiement à 30 jours",
        "Pour nos clients",
    ]
    assert prices(pro) == {"Écran 27": Decimal("40500"), "Clavier": Decimal("4500")}


async def test_hidden_sections_languages_and_no_product_twice(
    db_session: AsyncSession,
) -> None:
    await _shop(db_session)
    admin = await _admin(db_session)
    await _section(db_session, admin, kind="featured", config={"limit": 2})
    await _section(db_session, admin, kind="featured", title="Encore")
    await _section(db_session, admin, kind="categories", is_published=False)
    await _section(
        db_session,
        admin,
        kind="banner",
        title="English only",
        audience={"locales": ["en"]},
    )

    sections = await _page_of(db_session, None)
    assert [s.kind for s in sections] == ["featured", "featured"]
    first, second = sections
    assert first.title == "" and first.config == {"limit": 2, "layout": "grid"}
    assert len(first.products) == 2
    # The same products further down are not shown twice.
    assert second.products == []


async def test_reorder_in_one_call_and_refuse_a_stale_list(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    a = await _section(db_session, admin, kind="banner", title="A")
    b = await _section(db_session, admin, kind="banner", title="B")
    c = await _section(db_session, admin, kind="popular")

    ordered = await reorder_blocks(
        HomepageOrder(ids=[c, a, b]),
        _request(),
        db_session,
        await _fresh(db_session, admin),
    )
    assert [s.id for s in ordered] == [c, a, b]
    listed = await list_blocks(_request(), db_session, await _fresh(db_session, admin))
    assert [s.id for s in listed] == [c, a, b]
    assert [s.position for s in listed] == [0, 1, 2]

    # Replacing a section keeps its place.
    await replace_block(
        a,
        HomepageBlockWrite(
            kind="banner", title="A bis", is_published=True, position=99
        ),
        _request(),
        db_session,
        await _fresh(db_session, admin),
    )
    listed = await list_blocks(_request(), db_session, await _fresh(db_session, admin))
    assert [s.title for s in listed] == ["", "A bis", "B"]

    for stale in ([c, a], [c, a, b, b], [c, a, uuid.uuid4()]):
        with pytest.raises(AppError) as refused:
            await reorder_blocks(
                HomepageOrder(ids=stale),
                _request(),
                db_session,
                await _fresh(db_session, admin),
            )
        assert refused.value.code == "homepage.order_conflict"
        assert refused.value.status_code == 409


async def test_one_live_hero_per_audience(db_session: AsyncSession) -> None:
    shop = await _shop(db_session)
    admin = await _admin(db_session)
    now = datetime.datetime.now(datetime.UTC)
    await _section(
        db_session,
        admin,
        kind="hero",
        title="Visiteurs",
        audience={"scope": "guest"},
        starts_at=now,
    )
    # Customers never see the visitors' hero: both may run together.
    await _section(
        db_session, admin, kind="hero", title="Clients", audience={"scope": "customer"}
    )
    # A hero for everyone would hide behind both.
    with pytest.raises(AppError) as refused:
        await _section(db_session, admin, kind="hero", title="Tous")
    assert refused.value.code == "homepage.hero.conflict"
    # A pro-only hero overlaps the customers' one.
    with pytest.raises(AppError):
        await _section(
            db_session,
            admin,
            kind="hero",
            title="Pros",
            audience={"scope": "customer", "price_group_ids": [str(shop["pro_group"])]},
        )


async def test_collections_by_source_and_chosen_categories(
    db_session: AsyncSession,
) -> None:
    from app.features.content.homepage_collections import collection_products
    from app.features.discount.models import Discount, DiscountTarget, DiscountType
    from app.features.product.models.category import Category

    await _shop(db_session)
    admin = await _admin(db_session)
    screens = Category(name="Écrans")
    network = Category(name="Réseau")
    db_session.add_all([screens, network])
    await db_session.flush()
    wifi = Category(name="Wi-Fi", parent_id=network.id)
    db_session.add(wifi)
    await db_session.flush()
    products = {}
    for name, category, price in (
        ("Borne Wi-Fi", wifi, "9000"),
        ("Écran 24", screens, "30000"),
        ("Caché", screens, "1000"),
    ):
        product = Product(
            name=name,
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal(price),
            category_id=category.id,
            is_enriched=True,
            weight=1.0,
            customs_rate_pct=Decimal("0"),
            is_admin_active=name != "Caché",
        )
        db_session.add(product)
        await db_session.flush()
        products[name] = product.id
    db_session.add(
        Discount(
            name="Réseau −10 %",
            discount_type=DiscountType.PROMOTION,
            target=DiscountTarget.CATEGORY,
            category_id=network.id,
            percentage=Decimal("10"),
        )
    )
    network_id, screens_id = network.id, screens.id
    await db_session.commit()

    await _section(
        db_session,
        admin,
        kind="collection",
        title="Réseau",
        config={"source": "category", "category_id": str(network_id)},
    )
    await _section(
        db_session,
        admin,
        kind="collection",
        title="Promos",
        config={"source": "promotion"},
    )
    await _section(
        db_session,
        admin,
        kind="collection",
        title="Choix",
        config={"source": "manual"},
        items=[
            {"product_id": str(products["Écran 24"])},
            {"product_id": str(products["Caché"])},
            {"product_id": str(products["Borne Wi-Fi"])},
        ],
    )
    await _section(
        db_session,
        admin,
        kind="categories",
        config={"mode": "manual"},
        items=[
            {"category_id": str(network_id), "label": "Tout le réseau"},
            {"category_id": str(screens_id)},
        ],
    )

    sections = {s.title: s for s in await _page_of(db_session, None)}
    names = {t: [p.name for p in s.products or []] for t, s in sections.items()}
    # A sub-category belongs to its parent; a hidden product never shows; a
    # product already shown higher on the page is not shown again.
    assert names["Réseau"] == ["Borne Wi-Fi"]
    assert names["Promos"] == []
    assert names["Choix"] == ["Écran 24"]
    by_source = {
        s.title: [p.name for p in await collection_products(db_session, s.id, s.config)]
        for s in sections.values()
        if s.kind == "collection"
    }
    assert by_source["Promos"] == ["Borne Wi-Fi"]  # the promotion on « Réseau »
    assert by_source["Choix"] == ["Écran 24", "Borne Wi-Fi"]  # listed order
    tiles = next(s for s in sections.values() if s.kind == "categories").categories
    assert [t.title for t in tiles or []] == ["Tout le réseau", "Écrans"]

    # A category is required for that source, and only for it.
    for config in (
        {"source": "category"},
        {"source": "newest", "category_id": str(network_id)},
    ):
        with pytest.raises(AppError) as refused:
            await _section(db_session, admin, kind="collection", config=config)
        assert refused.value.code == "homepage.config"
    with pytest.raises(AppError) as refused:
        await _section(
            db_session,
            admin,
            kind="collection",
            config={"source": "manual"},
            items=[{"product_id": str(uuid.uuid4())}],
        )
    assert refused.value.code == "homepage.items"


async def test_best_sellers_count_a_variant_for_its_product(
    db_session: AsyncSession,
) -> None:
    """A product with compulsory variants sells only as a variant: its sales
    go to the parent the storefront lists (they were dropped)."""
    from app.features.content.homepage_collections import collection_products
    from app.features.order.models.order import Order
    from app.features.order.models.order_line import OrderLine
    from app.features.order.models.order_status import OrderStatus

    def item(name: str, **fields: Any) -> Product:
        return Product(
            name=name,
            pricing_mode=PricingMode.FIXED,
            base_price=Decimal("1000"),
            is_enriched=True,
            weight=1.0,
            customs_rate_pct=Decimal("0"),
            **fields,
        )

    shirt, cable = item("T-shirt", has_variants=True), item("Câble")
    db_session.add_all([shirt, cable])
    await db_session.flush()
    size_m = item("T-shirt M", parent_product_id=shirt.id)
    paid = OrderStatus(name="Paid")
    abandoned = OrderStatus(name="Pending")
    buyer = User(email=f"b+{uuid.uuid4().hex[:6]}@t.local", hashed_password="x")
    db_session.add_all([size_m, paid, abandoned, buyer])
    await db_session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=paid.id,
        total_amount=Decimal("1"),
        subtotal_amount=Decimal("1"),
        created_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(order)
    await db_session.flush()
    # An abandoned payment (Pending) sold nothing.
    unpaid = Order(
        user_id=buyer.id,
        order_status_id=abandoned.id,
        total_amount=Decimal("1"),
        subtotal_amount=Decimal("1"),
        created_at=datetime.datetime.now(datetime.UTC),
    )
    db_session.add(unpaid)
    await db_session.flush()
    db_session.add(
        OrderLine(
            order_id=unpaid.id,
            product_id=cable.id,
            quantity=50,
            unit_price=Decimal("1"),
        )
    )
    for product, quantity in ((size_m, 20), (cable, 3)):
        db_session.add(
            OrderLine(
                order_id=order.id,
                product_id=product.id,
                quantity=quantity,
                unit_price=Decimal("1"),
            )
        )
    await db_session.commit()

    found = await collection_products(
        db_session, uuid.uuid4(), {"source": "best_sellers", "limit": 4, "days": 30}
    )
    assert [p.name for p in found] == ["T-shirt", "Câble"]
