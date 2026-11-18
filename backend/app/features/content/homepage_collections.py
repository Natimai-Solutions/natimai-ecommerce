"""Product selections and chosen categories of the homepage (chantier accueil
et messagerie, lot A2, R2 and R3).

A **collection** shows products from a source:

- ``manual``: the products listed in the section, in their order;
- ``category``: a category and its sub-categories;
- ``newest``: the latest products;
- ``promotion``: the products a promotion in force covers (an article, or a
  category with its sub-categories). The struck-through price is computed per
  customer: a customer whose group price is already lower may see no
  discount on a card of this selection (accepted);
- ``popular``: the most viewed over ``days``;
- ``best_sellers``: the most ordered over ``days``.

Price sorts follow the reference price (``sale_price_cached``), as the
search does, not the customer's group price. Every source keeps to what the
catalogue may show (``storefront_conditions``): a selection never shows a
product the search hides.
"""

from __future__ import annotations

import datetime
import uuid
from typing import Any

from sqlalchemy import func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.datetimes import utcnow
from app.features.content.models import HomepageBlockItem
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.product.crud.product import crud_product
from app.features.product.models.category import Category
from app.features.product.models.product import Product
from app.features.product.services.category_tree import load_tree, subtree_ids
from app.features.product.services.group_pricing import load_active_promotions
from app.features.product.services.popularity import popular_products

#: Orders that did not happen do not make a best seller.
_NOT_SOLD = ("Cancelled", "PaymentFailed", "Refunded")


async def section_items(
    session: AsyncSession, block_id: uuid.UUID
) -> list[HomepageBlockItem]:
    rows = await session.exec(
        select(HomepageBlockItem)
        .where(col(HomepageBlockItem.block_id) == block_id)
        .order_by(col(HomepageBlockItem.position))
    )
    return list(rows.all())


def _sorted(statement: Any, sort: str) -> Any:
    if sort == "price_asc":
        return statement.order_by(col(Product.sale_price_cached).asc().nulls_last())
    if sort == "price_desc":
        return statement.order_by(col(Product.sale_price_cached).desc().nulls_last())
    if sort == "name":
        return statement.order_by(col(Product.name).asc())
    return statement.order_by(col(Product.created_at).desc().nulls_last())


async def collection_products(
    session: AsyncSession, block_id: uuid.UUID, config: dict[str, Any]
) -> list[Product]:
    """The products of a collection section, at most ``limit``."""
    source = config.get("source", "newest")
    limit = int(config.get("limit", 8))
    sort = str(config.get("sort", "newest"))
    days = int(config.get("days", 30))
    visible = crud_product.storefront_conditions()

    if source == "manual":
        ids = [
            i.product_id for i in await section_items(session, block_id) if i.product_id
        ]
        if not ids:
            return []
        rows = await session.exec(
            select(Product).where(col(Product.id).in_(ids), *visible)
        )
        by_id = {p.id: p for p in rows.all()}
        products = [by_id[i] for i in ids if i in by_id][:limit]
    elif source == "popular":
        products = await popular_products(
            session, conditions=visible, days=days, limit=limit
        )
    elif source == "best_sellers":
        since = utcnow() - datetime.timedelta(days=days)
        sold = (
            select(OrderLine.product_id, func.sum(OrderLine.quantity).label("sold"))
            .join(Order, col(Order.id) == col(OrderLine.order_id))
            .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
            .where(
                col(Order.created_at) >= since,
                col(OrderStatus.name).not_in(_NOT_SOLD),
            )
            .group_by(col(OrderLine.product_id))
            .subquery()
        )
        rows = await session.exec(
            select(Product)
            .join(sold, sold.c.product_id == col(Product.id))
            .where(*visible)
            .order_by(sold.c.sold.desc(), col(Product.name))
            .limit(limit)
        )
        products = list(rows.all())
    else:
        statement = select(Product).where(*visible)
        if source == "category":
            category_id = config.get("category_id")
            if not category_id:
                return []
            tree = await load_tree(session)
            subtree = subtree_ids(tree, uuid.UUID(str(category_id)))
            statement = statement.where(col(Product.category_id).in_(subtree))
        elif source == "promotion":
            promotions = await load_active_promotions(session)
            if not promotions:
                return []
            tree = await load_tree(session)
            product_ids = {p.product_id for p in promotions if p.product_id}
            category_ids: set[uuid.UUID] = set()
            for promotion in promotions:
                if promotion.category_id:
                    category_ids |= subtree_ids(tree, promotion.category_id)
            statement = statement.where(
                or_(
                    col(Product.id).in_(product_ids),
                    col(Product.category_id).in_(category_ids),
                )
            )
        rows = await session.exec(_sorted(statement, sort).limit(limit))
        products = list(rows.all())
    await crud_product._apply_runtime_sale_prices(session, products)  # noqa: SLF001
    return products


async def chosen_categories(
    session: AsyncSession, block_id: uuid.UUID
) -> list[tuple[Category, HomepageBlockItem]]:
    """The categories of a « categories » section in manual mode, in order
    (inactive or merged ones left out)."""
    items = [i for i in await section_items(session, block_id) if i.category_id]
    if not items:
        return []
    rows = await session.exec(
        select(Category).where(
            col(Category.id).in_([i.category_id for i in items]),
            col(Category.is_active).is_(True),
            col(Category.is_admin_active).is_(True),
            col(Category.merged_into_id).is_(None),
        )
    )
    by_id = {c.id: c for c in rows.all()}
    return [(by_id[i.category_id], i) for i in items if i.category_id in by_id]


__all__ = ["chosen_categories", "collection_products", "section_items"]
