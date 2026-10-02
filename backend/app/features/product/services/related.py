"""« Complétez votre équipement » (R9 / T7).

For a product (its page) or a set of products (the cart), the accessories
are the manual links of kind ``accessory`` in their order, then the best
sellers of the categories suggested from the products' categories; the
alternatives are the manual links of kind ``alternative``. Only products the
storefront may show *and* sell right now are returned: a suggestion the
customer cannot add to the cart is noise.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.inventory.services.availability import (
    available_quantity_expression,
)
from app.features.order.models.order_line import OrderLine
from app.features.product.crud.product import crud_product
from app.features.product.models.product import BACKORDER_MODES, Product
from app.features.product.models.product_link import CategoryLink, ProductLink

#: Window of the « meilleures ventes » ranking.
SALES_WINDOW_DAYS = 90
DEFAULT_LIMIT = 8


@dataclass
class RelatedProducts:
    accessories: list[Product] = field(default_factory=list)
    alternatives: list[Product] = field(default_factory=list)


def _sellable_conditions() -> list[Any]:
    """Shown on the storefront and orderable now (stock, or a backorder mode)."""
    return [
        *crud_product.storefront_conditions(),
        col(Product.parent_product_id).is_(None),
        or_(
            available_quantity_expression() > 0,
            col(Product.availability_mode).in_(sorted(BACKORDER_MODES)),
        ),
    ]


async def _manual_links(
    session: AsyncSession, product_ids: Sequence[uuid.UUID], kind: str
) -> list[uuid.UUID]:
    """Linked product ids of ``kind``, in manual order (position, then creation)."""
    rows = (
        await session.exec(
            select(ProductLink.linked_product_id)
            .where(
                col(ProductLink.product_id).in_(list(product_ids)),
                col(ProductLink.kind) == kind,
            )
            .order_by(
                col(ProductLink.position).asc(), col(ProductLink.created_at).asc()
            )
        )
    ).all()
    seen: list[uuid.UUID] = []
    for linked in rows:
        if linked not in seen:
            seen.append(linked)
    return seen


async def _suggested_category_ids(
    session: AsyncSession, category_ids: Iterable[uuid.UUID]
) -> list[uuid.UUID]:
    ids = [c for c in category_ids if c is not None]
    if not ids:
        return []
    rows = (
        await session.exec(
            select(CategoryLink.suggested_category_id)
            .where(col(CategoryLink.category_id).in_(ids))
            .order_by(col(CategoryLink.position).asc())
        )
    ).all()
    out: list[uuid.UUID] = []
    for suggested in rows:
        if suggested not in out:
            out.append(suggested)
    return out


async def _sellable_by_id(
    session: AsyncSession, ids: Sequence[uuid.UUID]
) -> dict[uuid.UUID, Product]:
    if not ids:
        return {}
    rows = (
        await session.exec(
            select(Product).where(
                col(Product.id).in_(list(ids)), *_sellable_conditions()
            )
        )
    ).all()
    return {p.id: p for p in rows}


async def best_sellers_in_categories(
    session: AsyncSession,
    category_ids: Sequence[uuid.UUID],
    *,
    exclude: Iterable[uuid.UUID],
    limit: int,
) -> list[Product]:
    """Sellable products of the categories, most sold over the window first,
    then the most recent."""
    if not category_ids or limit <= 0:
        return []
    since = datetime.now(timezone.utc) - timedelta(days=SALES_WINDOW_DAYS)
    sold = (
        select(
            col(OrderLine.product_id).label("product_id"),
            func.coalesce(func.sum(col(OrderLine.quantity)), 0).label("sold"),
        )
        .where(
            or_(
                col(OrderLine.created_at).is_(None),
                col(OrderLine.created_at) >= since,
            )
        )
        .group_by(col(OrderLine.product_id))
        .subquery()
    )
    statement = (
        select(Product)
        .outerjoin(sold, sold.c.product_id == col(Product.id))
        .where(
            col(Product.category_id).in_(list(category_ids)),
            col(Product.id).not_in(list(exclude)) if exclude else True,
            *_sellable_conditions(),
        )
        .order_by(
            func.coalesce(sold.c.sold, 0).desc(),
            col(Product.created_at).desc(),
        )
        .limit(limit)
    )
    return list((await session.exec(statement)).all())


async def related_products(
    session: AsyncSession,
    product_ids: Sequence[uuid.UUID],
    *,
    limit: int = DEFAULT_LIMIT,
    exclude: Iterable[uuid.UUID] = (),
) -> RelatedProducts:
    """Accessories (manual links, then suggested categories' best sellers) and
    alternatives (manual links) for one or several products, without the
    products themselves nor ``exclude`` (the rest of the cart)."""
    if not product_ids:
        return RelatedProducts()
    excluded = set(product_ids) | set(exclude)
    products = list(
        (
            await session.exec(
                select(Product).where(col(Product.id).in_(list(product_ids)))
            )
        ).all()
    )
    if not products:
        return RelatedProducts()

    accessory_ids = [
        i
        for i in await _manual_links(session, product_ids, "accessory")
        if i not in excluded
    ]
    alternative_ids = [
        i
        for i in await _manual_links(session, product_ids, "alternative")
        if i not in excluded
    ]
    sellable = await _sellable_by_id(session, [*accessory_ids, *alternative_ids])
    accessories = [sellable[i] for i in accessory_ids if i in sellable][:limit]
    alternatives = [sellable[i] for i in alternative_ids if i in sellable][:limit]

    room = limit - len(accessories)
    if room > 0:
        suggested = await _suggested_category_ids(
            session, (p.category_id for p in products if p.category_id)
        )
        accessories += await best_sellers_in_categories(
            session,
            suggested,
            exclude=excluded | {p.id for p in accessories},
            limit=room,
        )
    return RelatedProducts(accessories=accessories, alternatives=alternatives)


async def replace_product_links(
    session: AsyncSession, product: Product, items: Sequence[Any]
) -> list[ProductLink]:
    """Replace the manual links of ``product`` (no commit). ``items`` carry
    ``linked_product_id``, ``kind`` and ``position``; a link to the product
    itself or to an unknown product is refused (``ValueError``)."""
    from app.features.product.models.product_link import LINK_KINDS

    wanted: list[tuple[uuid.UUID, str, int]] = []
    for item in items:
        linked = item.linked_product_id
        kind = str(item.kind)
        if linked == product.id:
            raise ValueError("un article ne peut pas être lié à lui-même")
        if kind not in LINK_KINDS:
            raise ValueError(f"type de lien inconnu : {kind}")
        if (linked, kind) not in [(w[0], w[1]) for w in wanted]:
            wanted.append((linked, kind, int(item.position)))
    targets: set[uuid.UUID] = set()
    if wanted:
        targets = set(
            (
                await session.exec(
                    select(col(Product.id)).where(
                        col(Product.id).in_([w[0] for w in wanted])
                    )
                )
            ).all()
        )
    missing = [w[0] for w in wanted if w[0] not in targets]
    if missing:
        raise ValueError(f"article introuvable : {missing[0]}")

    existing = list(
        (
            await session.exec(
                select(ProductLink).where(ProductLink.product_id == product.id)
            )
        ).all()
    )
    for row in existing:
        await session.delete(row)
    await session.flush()
    now = datetime.now(timezone.utc)
    rows = [
        ProductLink(
            product_id=product.id,
            linked_product_id=linked,
            kind=kind,
            position=position,
            created_at=now,
        )
        for linked, kind, position in wanted
    ]
    session.add_all(rows)
    await session.flush()
    return rows


async def replace_category_links(
    session: AsyncSession, category_id: uuid.UUID, suggested: Sequence[uuid.UUID]
) -> None:
    """Replace the suggested categories of ``category_id`` (no commit)."""
    for row in (
        await session.exec(
            select(CategoryLink).where(CategoryLink.category_id == category_id)
        )
    ).all():
        await session.delete(row)
    await session.flush()
    seen: list[uuid.UUID] = []
    for suggested_id in suggested:
        if suggested_id != category_id and suggested_id not in seen:
            seen.append(suggested_id)
    session.add_all(
        CategoryLink(category_id=category_id, suggested_category_id=s, position=i)
        for i, s in enumerate(seen)
    )
    await session.flush()


async def suggested_categories_map(
    session: AsyncSession, category_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, list[uuid.UUID]]:
    ids = list(category_ids)
    if not ids:
        return {}
    rows = (
        await session.exec(
            select(CategoryLink)
            .where(col(CategoryLink.category_id).in_(ids))
            .order_by(col(CategoryLink.position).asc())
        )
    ).all()
    out: dict[uuid.UUID, list[uuid.UUID]] = {}
    for row in rows:
        out.setdefault(row.category_id, []).append(row.suggested_category_id)
    return out
