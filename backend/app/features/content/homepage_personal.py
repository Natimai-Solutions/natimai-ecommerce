"""The personal sections of the homepage (chantier accueil et messagerie,
lot A5 / R9), for a signed-in customer only: what they bought before, their
wishlist, their order in progress. « Recently viewed » lives in the
customer's browser (no history kept on the server)."""

from __future__ import annotations

import uuid

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.content.models import HomepageCurrentOrder
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.product.crud.product import crud_product
from app.features.product.models.product import Product
from app.features.user.models.wishlist import Wishlist, WishlistItem

#: An order still worth showing on the homepage: not delivered nor closed.
_CLOSED_STATUSES = frozenset(
    {"Delivered", "Cancelled", "Refunded", "PartiallyRefunded"}
)


async def _products(
    session: AsyncSession, ids: list[uuid.UUID], limit: int
) -> list[Product]:
    """The products of ``ids`` still on sale, in that order."""
    if not ids:
        return []
    rows = (
        await session.exec(
            select(Product).where(
                col(Product.id).in_(ids), *crud_product.storefront_conditions()
            )
        )
    ).all()
    by_id = {p.id: p for p in rows}
    found = [by_id[i] for i in ids if i in by_id][:limit]
    await crud_product._apply_runtime_sale_prices(session, found)  # noqa: SLF001
    return found


async def reorder_products(
    session: AsyncSession, user_id: uuid.UUID, limit: int
) -> list[Product]:
    """What the customer bought, the latest first, each product once."""
    rows = (
        await session.exec(
            select(OrderLine.product_id, Order.created_at)
            .join(Order, col(Order.id) == col(OrderLine.order_id))
            .where(col(Order.user_id) == user_id)
            .order_by(col(Order.created_at).desc())
            .limit(200)
        )
    ).all()
    ids = list(dict.fromkeys(product_id for product_id, _ in rows if product_id))
    return await _products(session, ids, limit)


async def wishlist_products(
    session: AsyncSession, user_id: uuid.UUID, limit: int
) -> list[Product]:
    """The products of the customer's wishlists, the latest added first."""
    rows = (
        await session.exec(
            select(WishlistItem.product_id)
            .join(Wishlist, col(Wishlist.id) == col(WishlistItem.wishlist_id))
            .where(col(Wishlist.user_id) == user_id)
            .order_by(col(WishlistItem.created_at).desc())
            .limit(200)
        )
    ).all()
    return await _products(session, list(dict.fromkeys(rows)), limit)


async def current_order(
    session: AsyncSession, user_id: uuid.UUID
) -> HomepageCurrentOrder | None:
    """The customer's latest order not yet delivered nor closed."""
    rows = (
        await session.exec(
            select(Order, OrderStatus.name)
            .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
            .where(col(Order.user_id) == user_id)
            .order_by(col(Order.created_at).desc())
            .limit(5)
        )
    ).all()
    for order, status in rows:
        if status in _CLOSED_STATUSES:
            continue
        return HomepageCurrentOrder(
            id=order.id,
            order_number=order.order_number,
            status=status,
            created_at=order.created_at,
            total_amount=str(order.total_amount),
            currency=order.currency,
        )
    return None


__all__ = [
    "HomepageCurrentOrder",
    "current_order",
    "reorder_products",
    "wishlist_products",
]
