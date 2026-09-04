"""Catégories : titre vitrine, fusion et résolution par la sync (A17 / A12), vraie base.

Ce qui doit tenir : renommer côté vitrine ne touche pas la clé de rapprochement ;
une fusion déplace produits et remises, laisse la source inactive et pointée
vers la cible ; la synchronisation qui rencontre encore le nom de la source
atterrit sur la cible au lieu de recréer une catégorie.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_categories import (
    AdminCategoryUpdate,
    MergeBody,
    list_categories,
    merge_category,
    update_category,
)
from app.core.errors import AppError
from app.features.discount.models import Discount, DiscountTarget, DiscountType
from app.features.product.crud.category import crud_category
from app.features.product.models.category import Category
from app.features.product.models.product import Product
from app.features.user.models.user import User


async def _seed_admin(session: AsyncSession) -> User:
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    session.add(admin)
    await session.flush()
    return admin


async def _seed_categories(session: AsyncSession) -> tuple[Category, Category]:
    source = Category(name="NOTEBOOKS", is_active=True)
    target = Category(name="Ordinateurs portables", is_active=True)
    session.add_all([source, target])
    await session.flush()
    session.add_all(
        [
            Product(name="Laptop A", category_id=source.id),
            Product(name="Laptop B", category_id=source.id),
            Product(name="Laptop C", category_id=target.id),
            Discount(
                name="Promo notebooks",
                discount_type=DiscountType.PROMOTION,
                percentage=Decimal("10.00"),
                target=DiscountTarget.CATEGORY,
                category_id=source.id,
            ),
        ]
    )
    await session.flush()
    return source, target


@pytest.mark.asyncio
async def test_display_name_never_touches_the_sync_key(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    source, _ = await _seed_categories(db_session)
    source_id, admin_id = source.id, admin.id

    item = await update_category(
        source_id,
        AdminCategoryUpdate(display_name="  Portables  ", description="Nos portables"),
        db_session,
        cast(Any, admin),
    )
    assert item.name == "NOTEBOOKS"
    assert item.display_name == "Portables"
    assert item.title == "Portables"
    assert item.product_count == 2

    # La sync retrouve toujours la catégorie par son nom d'origine.
    found, created = await crud_category.get_or_create_by_name(
        db_session, name="notebooks"
    )
    assert created is False
    assert found.id == source_id

    # Reposer le nom lui-même comme titre = pas de personnalisation.
    admin_row = await db_session.get(User, admin_id)
    item = await update_category(
        source_id,
        AdminCategoryUpdate(display_name="NOTEBOOKS"),
        db_session,
        cast(Any, admin_row),
    )
    assert item.display_name is None
    assert item.title == "NOTEBOOKS"


@pytest.mark.asyncio
async def test_merge_moves_products_and_keeps_resolving_the_old_name(
    db_session: AsyncSession,
) -> None:
    admin = await _seed_admin(db_session)
    source, target = await _seed_categories(db_session)
    source_id, target_id, admin_id = source.id, target.id, admin.id

    result = await merge_category(
        source_id, MergeBody(target_id=target_id), db_session, cast(Any, admin)
    )
    assert result.moved_products == 2
    assert result.moved_discounts == 1
    assert result.target.product_count == 3
    assert result.source.product_count == 0
    assert result.source.is_active is False
    assert result.source.merged_into_id == target_id
    assert result.source.merged_into_name == "Ordinateurs portables"

    # La sync qui rencontre encore « NOTEBOOKS » atterrit sur la cible.
    found, created = await crud_category.get_or_create_by_name(
        db_session, name="NOTEBOOKS"
    )
    assert created is False
    assert found.id == target_id

    # La liste admin montre la source comme fusionnée, la cible avec ses produits.
    admin_row = await db_session.get(User, admin_id)
    listed = await list_categories(db_session, cast(Any, admin_row))
    by_id = {c.id: c for c in listed.data}
    assert by_id[source_id].merged_into_name == "Ordinateurs portables"
    assert by_id[target_id].product_count == 3

    # Une source fusionnée ne se réactive pas et ne se refusionne pas.
    admin_row = await db_session.get(User, admin_id)
    with pytest.raises(AppError) as exc:
        await update_category(
            source_id,
            AdminCategoryUpdate(is_active=True),
            db_session,
            cast(Any, admin_row),
        )
    assert exc.value.code == "category.merged"

    admin_row = await db_session.get(User, admin_id)
    with pytest.raises(AppError) as exc:
        await merge_category(
            source_id, MergeBody(target_id=target_id), db_session, cast(Any, admin_row)
        )
    assert exc.value.code == "category.merged"


@pytest.mark.asyncio
async def test_merge_refuses_self_and_merged_targets(db_session: AsyncSession) -> None:
    admin = await _seed_admin(db_session)
    source, target = await _seed_categories(db_session)
    third = Category(name="Tiers", is_active=True)
    db_session.add(third)
    await db_session.flush()
    source_id, target_id, third_id, admin_id = source.id, target.id, third.id, admin.id

    with pytest.raises(AppError) as exc:
        await merge_category(
            source_id, MergeBody(target_id=source_id), db_session, cast(Any, admin)
        )
    assert exc.value.code == "category.merge.self"

    await merge_category(
        source_id, MergeBody(target_id=target_id), db_session, cast(Any, admin)
    )

    # Fusionner vers une catégorie déjà absorbée est refusé : la cible doit
    # être la survivante, pas un alias.
    admin_row = await db_session.get(User, admin_id)
    with pytest.raises(AppError) as exc:
        await merge_category(
            third_id, MergeBody(target_id=source_id), db_session, cast(Any, admin_row)
        )
    assert exc.value.code == "category.merge.target_unavailable"


@pytest.mark.asyncio
async def test_sync_follows_a_merge_chain(db_session: AsyncSession) -> None:
    """A fusionnée dans B, puis B dans C : le nom de A doit résoudre vers C."""
    a = Category(name="A", is_active=False)
    b = Category(name="B", is_active=False)
    c = Category(name="C", is_active=True)
    db_session.add_all([a, b, c])
    await db_session.flush()
    a.merged_into_id = b.id
    b.merged_into_id = c.id
    db_session.add_all([a, b])
    await db_session.flush()
    c_id = c.id

    found, created = await crud_category.get_or_create_by_name(db_session, name="a")
    assert created is False
    assert found.id == c_id
