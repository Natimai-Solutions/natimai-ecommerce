"""Sellable quantity of a product: warehouse stock plus supplier stock.

One definition, shared by the checkout reservation (``api/routes/cart.py``)
and the storefront (product reads, listings, search filter and grouping), so
what the customer sees as « en stock » is exactly what the checkout accepts:

* **local** — units physically held at the warehouse: the ``Inventory`` row
  of the product without a place (the one the checkout reserves from and the
  admin adjusts from « Inventaire »);
* **supplier** — ``Product.supplier_quantity``, which only counts when the
  product has a supplier: the synced ones and the manual ones linked to a
  declared supplier. A warehouse-only product has no supplier stock, whatever
  the column says.

Nothing here commits; the helpers only read.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Sequence
from decimal import Decimal
from typing import Any

from sqlalchemy import and_, case, func, or_
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.content_i18n import PRODUCT_FIELDS, localize_all
from app.features.inventory.models.inventory import Inventory
from app.features.product.models.product import Product, ProductPublic

ZERO = Decimal("0.00")


def has_supplier_stock(product: Any) -> bool:
    """Whether ``supplier_quantity`` is sellable stock for this product.

    Mirrors the checkout: a synced product, or a manual one linked to a
    supplier (``supplier_name``). A warehouse-only product has neither.
    """
    return bool(
        getattr(product, "is_supplier_managed", False)
        or getattr(product, "supplier_name", None)
    )


def supplier_available_quantity(product: Any) -> Decimal:
    """Supplier stock the checkout would draw from (0 without a supplier)."""
    if not has_supplier_stock(product):
        return ZERO
    return Decimal(str(getattr(product, "supplier_quantity", None) or 0))


def local_quantity_expression() -> Any:
    """SQL: warehouse stock of the ``Product`` row of the enclosing query.

    Correlated scalar subquery over the place-less ``Inventory`` row(s) —
    the same row the checkout reserves from. ``0`` when there is none.
    """
    return (
        select(func.coalesce(func.sum(col(Inventory.quantity)), 0))
        .where(
            col(Inventory.product_id) == col(Product.id),
            col(Inventory.place_id).is_(None),
            col(Inventory.is_active).is_(True),
        )
        .correlate(Product)
        .scalar_subquery()
    )


def supplier_quantity_expression() -> Any:
    """SQL twin of :func:`supplier_available_quantity`."""
    return case(
        (
            or_(
                col(Product.is_supplier_managed).is_(True),
                func.coalesce(col(Product.supplier_name), "") != "",
            ),
            col(Product.supplier_quantity),
        ),
        else_=0,
    )


def local_stock_expression() -> Any:
    """SQL: warehouse stock, the variants' included for a parent (« chez nous »)."""
    from app.features.product.services.variants import (
        children_local_quantity_expression,
    )

    return local_quantity_expression() + children_local_quantity_expression()


def supplier_stock_expression() -> Any:
    """SQL: supplier stock, the variants' included (« chez le fournisseur »)."""
    from app.features.product.services.variants import (
        children_supplier_quantity_expression,
    )

    return supplier_quantity_expression() + children_supplier_quantity_expression()


def available_quantity_expression() -> Any:
    """SQL: local + supplier stock, plus the variants' for a parent product."""
    from app.features.product.services.variants import (
        children_available_quantity_expression,
    )

    return (
        local_quantity_expression()
        + supplier_quantity_expression()
        + children_available_quantity_expression()
    )


async def local_quantities(
    session: AsyncSession, product_ids: Iterable[uuid.UUID]
) -> dict[uuid.UUID, Decimal]:
    """Warehouse stock per product, in one query; missing = no stock."""
    ids = list(product_ids)
    if not ids:
        return {}
    statement = (
        select(col(Inventory.product_id), func.sum(col(Inventory.quantity)))
        .where(
            col(Inventory.product_id).in_(ids),
            col(Inventory.place_id).is_(None),
            col(Inventory.is_active).is_(True),
        )
        .group_by(col(Inventory.product_id))
    )
    rows = await session.exec(statement)
    return {
        product_id: Decimal(str(quantity or 0)) for product_id, quantity in rows.all()
    }


#: ``customer`` of :func:`publish_with_availability` for back-office screens:
#: reference prices, whatever the admin's own group.
STAFF: Any = object()


async def publish_with_availability(
    session: AsyncSession, products: Sequence[Any], *, customer: Any = STAFF
) -> list[ProductPublic]:
    """Serialize products for the storefront with their sellable quantity.

    Sets ``local_quantity`` and ``available_quantity`` on each
    :class:`ProductPublic`. With ``customer`` (a user, or None for a visitor)
    the prices are the ones that customer pays: their group's price or
    discount (product/services/group_pricing.py); :data:`STAFF` keeps the
    reference prices.
    """
    from app.features.product.services.group_pricing import (
        price_publics,
        pricing_for_user,
    )
    from app.features.product.services.variants import (
        children_availability,
        stock_counts_variants,
    )

    publics = [ProductPublic.model_validate(product) for product in products]
    if customer is not STAFF:
        # Storefront read: texts in the request's language (R9 / T3). The
        # back-office (STAFF) keeps the source language it edits.
        localize_all(publics, PRODUCT_FIELDS)
    if customer is not STAFF and publics:
        pricing = await pricing_for_user(
            session, customer, (public.id for public in publics)
        )
        price_publics(publics, pricing)
    local = await local_quantities(session, (public.id for public in publics))
    parents = await children_availability(
        session, [public.id for public in publics if public.has_variants]
    )
    for public in publics:
        public.local_quantity = local.get(public.id, ZERO)
        children = parents.get(public.id)
        public.variants_count = children.count if children else 0
        # Sellable stock split by where it is: our warehouse, the supplier.
        # A parent counts its variants' stock — unless it is sold as is
        # (optional variants): its stock is then its own, as at the checkout.
        counted = children if children and stock_counts_variants(public) else None
        public.stock_local = public.local_quantity + (
            counted.local if counted else ZERO
        )
        public.stock_supplier = supplier_available_quantity(public) + (
            counted.supplier if counted else ZERO
        )
        public.available_quantity = public.stock_local + public.stock_supplier
    return publics


#: Orders whose supplier units are still ours to account for: the supplier
#: has not been ordered from yet, so its own count still includes them.
#: Past « OrderedFromSupplier » (or cancelled / refunded) they are the
#: supplier's business again.
NOT_YET_ORDERED_FROM_SUPPLIER: frozenset[str] = frozenset(
    {
        "Pending",
        "AwaitingPayment",
        "PartiallyPaid",
        "PaymentFailed",
        "PaymentReview",
        "Paid",
        "DepositPaid",
    }
)


async def outstanding_supplier_reservations(
    session: AsyncSession, product_ids: Any
) -> dict[Any, Decimal]:
    """Units of each product our orders took from the supplier's stock and
    that the supplier's own count still shows (audit 2026-11, B4).

    ``supplier_quantity`` is the supplier's count *less* these: a live
    check or a sync that wrote the raw count gave them back to sale, and the
    product was sold twice until the supplier order was placed. Pending
    reservations always count; confirmed ones (paid) while the order is not
    yet ordered from the supplier.
    """
    from app.features.inventory.models.stock_movement import (
        InventoryStockMovement,
        MovementStatus,
        MovementType,
        ReferenceType,
    )
    from app.features.inventory.services.stock_release import LOCAL_SEGMENT_MARKER
    from app.features.order.models.order import Order
    from app.features.order.models.order_status import OrderStatus

    ids = list({pid for pid in product_ids if pid is not None})
    if not ids:
        return {}
    movement = InventoryStockMovement
    statement = (
        select(movement.product_id, func.sum(col(movement.quantity)))
        .outerjoin(Order, col(Order.id) == col(movement.reference_id))
        .outerjoin(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
        .where(
            col(movement.product_id).in_(ids),
            movement.reference_type == ReferenceType.ORDER.value,
            movement.movement_type == MovementType.OUTGOING.value,
            col(movement.is_active).is_(True),
            or_(
                col(movement.reason).is_(None),
                ~col(movement.reason).contains(LOCAL_SEGMENT_MARKER),
            ),
            or_(
                col(movement.status) == MovementStatus.PENDING.value,
                and_(
                    col(movement.status) == MovementStatus.COMPLETED.value,
                    col(OrderStatus.name).in_(list(NOT_YET_ORDERED_FROM_SUPPLIER)),
                ),
            ),
        )
        .group_by(col(movement.product_id))
    )
    rows = (await session.exec(statement)).all()
    return {product_id: Decimal(total or 0) for product_id, total in rows}


async def net_supplier_quantity(
    session: AsyncSession, product_id: Any, supplier_count: Decimal
) -> Decimal:
    """The supplier's count less our outstanding reservations, never < 0."""
    held = (await outstanding_supplier_reservations(session, [product_id])).get(
        product_id, ZERO
    )
    return max(Decimal(supplier_count) - held, ZERO)
