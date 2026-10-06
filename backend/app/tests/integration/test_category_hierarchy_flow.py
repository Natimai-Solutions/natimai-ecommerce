"""Integration: categories with parents (real Postgres).

« Réseau > WiFi > Point d'accès WiFi » : the admin ranks a category under
another, the sub-category inherits the customs rate and the margin its
branch leaves unset (pricing context, resolvers, publication gate), the
storefront search on « Réseau » lists the access points, the parent guard
refuses cycles, and a merge moves the sub-categories along.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_categories import (
    AdminCategoryCreate,
    AdminCategoryUpdate,
    MergeBody,
    create_category,
    list_categories,
    merge_category,
    update_category,
)
from app.core.errors import AppError
from app.features.product.crud.product import crud_product
from app.features.product.models.category import Category
from app.features.product.models.product import PricingMode, Product
from app.features.product.services.pricing import (
    PricingContext,
    resolve_customs_rate_pct,
    resolve_margin_rate_pct,
)
from app.features.product.services.publication import customs_rate_condition
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
    return admin


async def _fresh(session: AsyncSession, user: User) -> User:
    await session.refresh(user)
    return user


async def _create(
    session: AsyncSession, admin: User, name: str, parent_id: uuid.UUID | None = None
) -> uuid.UUID:
    item = await create_category(
        payload=AdminCategoryCreate(name=name, parent_id=parent_id),
        session=session,
        current_user=await _fresh(session, admin),
    )
    return item.id


@pytest.mark.asyncio
async def test_sub_categories_inherit_defaults_and_are_listed_under_their_parent(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    reseau = await _create(db_session, admin, "Réseau")
    wifi = await _create(db_session, admin, "WiFi", reseau)
    ap = await _create(db_session, admin, "Point d'accès WiFi", wifi)
    ecrans = await _create(db_session, admin, "Écrans")

    root = await db_session.get(Category, reseau)
    assert root is not None
    root.default_customs_rate_pct = Decimal("12.5")
    root.default_margin_rate_pct = Decimal("40")
    middle = await db_session.get(Category, wifi)
    assert middle is not None
    middle.default_margin_rate_pct = Decimal("35")
    db_session.add_all([root, middle])
    product = Product(
        name="Point d'accès UniFi",
        category_id=ap,
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("25000"),
        weight=0.5,
        is_enriched=True,
    )
    screen = Product(
        name="Écran 24",
        category_id=ecrans,
        pricing_mode=PricingMode.FIXED,
        base_price=Decimal("30000"),
        is_enriched=True,
    )
    db_session.add_all([product, screen])
    await db_session.commit()

    # The admin list: tree order, path, level and the values in force.
    listing = await list_categories(
        session=db_session, _current_user=await _fresh(db_session, admin)
    )
    by_id = {item.id: item for item in listing.data}
    assert by_id[ap].path == ["Réseau", "WiFi", "Point d'accès WiFi"]
    assert (
        by_id[ap].depth,
        by_id[wifi].children_count,
        by_id[reseau].children_count,
    ) == (
        2,
        1,
        1,
    )
    assert by_id[ap].parent_id == wifi and by_id[ap].parent_name == "WiFi"
    assert by_id[ap].default_customs_rate_pct is None
    assert by_id[ap].inherited_customs_rate_pct == Decimal("12.50")
    assert by_id[ap].inherited_customs_rate_from == "Réseau"
    assert by_id[ap].inherited_margin_rate_pct == Decimal("35.00")
    assert by_id[ap].inherited_margin_rate_from == "WiFi"
    assert by_id[wifi].inherited_margin_rate_from is None  # its own value
    order = [item.id for item in listing.data if item.id in {reseau, wifi, ap, ecrans}]
    assert order.index(reseau) < order.index(wifi) < order.index(ap)

    # Pricing reads the inherited rates: the context and the resolvers alike.
    await db_session.refresh(product)
    await db_session.refresh(screen)
    context = await PricingContext.load(db_session)
    assert context.customs_rate_pct(product) == Decimal("12.50")
    assert context.margin_rate_pct(product) == Decimal("35.00")
    assert context.customs_rate_pct(screen) is None
    assert await resolve_customs_rate_pct(db_session, product) == Decimal("12.50")
    assert await resolve_margin_rate_pct(db_session, product, group=None) == Decimal(
        "35.00"
    )
    # …and so does the publication gate (SQL).
    publishable = set(
        (
            await db_session.exec(
                select(col(Product.id)).where(
                    customs_rate_condition(),
                    col(Product.id).in_([product.id, screen.id]),
                )
            )
        ).all()
    )
    assert publishable == {product.id}

    # The storefront: « Réseau » lists the access point, « Écrans » does not.
    screen.customs_rate_pct = Decimal("0")
    db_session.add(screen)
    await db_session.commit()
    from app.tasks.pricing_tasks import refresh_sale_prices

    await refresh_sale_prices(db_session)
    names = {
        p.name
        for p in (
            await crud_product.search_products(
                db_session, category_id=reseau, group_offers=False
            )
        )["data"]
    }
    assert names == {"Point d'accès UniFi"}
    assert {
        p.name
        for p in (
            await crud_product.search_products(
                db_session, category_id=ap, group_offers=False
            )
        )["data"]
    } == {"Point d'accès UniFi"}


@pytest.mark.asyncio
async def test_the_parent_guard_and_the_merge_keep_the_tree_sound(
    db_session: AsyncSession,
) -> None:
    admin = await _admin(db_session)
    reseau = await _create(db_session, admin, "Réseau")
    wifi = await _create(db_session, admin, "WiFi", reseau)
    ap = await _create(db_session, admin, "Point d'accès WiFi", wifi)
    sans_fil = await _create(db_session, admin, "Sans fil", reseau)

    async def move(category_id: uuid.UUID, parent_id: uuid.UUID | None) -> Any:
        return await update_category(
            category_id=category_id,
            payload=AdminCategoryUpdate(parent_id=parent_id),
            session=db_session,
            current_user=await _fresh(db_session, admin),
        )

    with pytest.raises(AppError) as cycle:
        await move(reseau, ap)
    assert cycle.value.code == "category.parent.cycle"
    with pytest.raises(AppError) as itself:
        await move(wifi, wifi)
    assert itself.value.code == "category.parent.cycle"
    with pytest.raises(AppError) as unknown:
        await move(wifi, uuid.uuid4())
    assert unknown.value.code == "category.parent.not_found"

    moved = await move(ap, reseau)
    assert moved.path == ["Réseau", "Point d'accès WiFi"]
    moved = await move(ap, wifi)
    assert moved.path == ["Réseau", "WiFi", "Point d'accès WiFi"]
    top = await move(wifi, None)
    assert top.path == ["WiFi"] and top.depth == 0

    # Merging WiFi into « Sans fil »: the access point follows.
    with pytest.raises(AppError) as below:
        await merge_category(
            category_id=reseau,
            payload=MergeBody(target_id=sans_fil),
            session=db_session,
            current_user=await _fresh(db_session, admin),
        )
    assert below.value.code == "category.merge.target_below_source"
    result = await merge_category(
        category_id=wifi,
        payload=MergeBody(target_id=sans_fil),
        session=db_session,
        current_user=await _fresh(db_session, admin),
    )
    assert result.source.merged_into_id == sans_fil
    leaf = await db_session.get(Category, ap)
    assert leaf is not None
    await db_session.refresh(leaf)
    assert leaf.parent_id == sans_fil
    listing = await list_categories(
        session=db_session, _current_user=await _fresh(db_session, admin)
    )
    assert {i.id: i.path for i in listing.data}[ap] == [
        "Réseau",
        "Sans fil",
        "Point d'accès WiFi",
    ]
    assert cast(Any, {i.id: i for i in listing.data}[sans_fil]).children_count == 1
