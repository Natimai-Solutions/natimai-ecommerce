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

#: Orders that did not happen: never « bought », never « in progress »
#: (an abandoned or failed payment stays Pending / PaymentFailed).
_NOT_PLACED = ("Pending", "PaymentFailed", "Cancelled", "Refunded")
#: An order in progress: placed, not yet delivered nor closed.
_NOT_IN_PROGRESS = (*_NOT_PLACED, "Delivered", "PartiallyRefunded")


async def _products(
    session: AsyncSession, ids: list[uuid.UUID], limit: int
) -> list[Product]:
    """The products of ``ids`` still on sale, in that order. A variant
    (« T-shirt M », what an order line or a wish holds) stands for the
    product the storefront lists, its parent; each product once."""
    if not ids:
        return []
    parents = dict(
        (
            await session.exec(
                select(Product.id, Product.parent_product_id).where(
                    col(Product.id).in_(ids),
                    col(Product.parent_product_id).is_not(None),
                )
            )
        ).all()
    )
    ids = list(dict.fromkeys(parents.get(i) or i for i in ids))
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
            .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
            .where(
                col(Order.user_id) == user_id,
                col(OrderStatus.name).not_in(_NOT_PLACED),
            )
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
            .where(
                col(Wishlist.user_id) == user_id,
                # A product removed from the list is deactivated, not deleted.
                col(WishlistItem.is_active).is_(True),
                col(WishlistItem.is_admin_active).is_(True),
                col(Wishlist.is_active).is_(True),
                col(Wishlist.is_admin_active).is_(True),
            )
            .order_by(col(WishlistItem.created_at).desc())
            .limit(200)
        )
    ).all()
    return await _products(session, list(dict.fromkeys(rows)), limit)


async def current_order(
    session: AsyncSession, user_id: uuid.UUID
) -> HomepageCurrentOrder | None:
    """The customer's latest order not yet delivered nor closed."""
    row = (
        await session.exec(
            select(Order, OrderStatus.name)
            .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
            .where(
                col(Order.user_id) == user_id,
                col(OrderStatus.name).not_in(_NOT_IN_PROGRESS),
            )
            .order_by(col(Order.created_at).desc())
            .limit(1)
        )
    ).first()
    if row is not None:
        order, status = row
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
