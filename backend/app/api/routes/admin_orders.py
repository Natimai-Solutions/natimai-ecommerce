"""Admin-facing client-order endpoints (superuser only).

Provides a list + rich detail view of customer orders for back-office use
(the payment-validation screen links here). The default CRUD `OrderPublic`
lacks client names, status names, lines and payments, so this module assembles
an enriched view.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter
from pydantic import BaseModel
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.providers import provider_supports_in_app_refund
from app.features.product.models.product import Product
from app.features.user.models.user import User

router = APIRouter(prefix="/admin/orders", tags=["admin-order"])


class AdminOrderListItem(BaseModel):
    """Represents an admin order list row."""

    order_id: uuid.UUID
    created_at: datetime | None = None
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    status: str | None = None
    total_amount: float


class AdminOrderLineItem(BaseModel):
    """Represents an order line in the admin detail view."""

    product_id: uuid.UUID
    product_name: str | None = None
    quantity: int
    unit_price: float
    line_total: float


# Payment status names from which a refund can still be issued.
_REFUNDABLE_PAYMENT_STATUSES = {"Completed", "PartiallyRefunded"}


class AdminOrderPaymentItem(BaseModel):
    """Represents a payment attached to an order in the admin detail view."""

    payment_id: uuid.UUID
    provider_code: str | None = None
    provider_reference: str | None = None
    amount: float
    currency: str
    status: str | None = None
    created_at: datetime | None = None
    # True when the admin UI may initiate a refund: the provider supports an
    # in-app refund (card / PayZen) and the payment is in a refundable state.
    can_refund: bool = False


class AdminOrderDetail(BaseModel):
    """Represents the enriched admin order detail."""

    order_id: uuid.UUID
    created_at: datetime | None = None
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    status: str | None = None
    subtotal_amount: float
    shipping_fee_amount: float
    payment_fee_amount: float
    total_fees_amount: float
    total_amount: float
    shipping_address: str | None = None
    notes: str | None = None
    lines: list[AdminOrderLineItem]
    payments: list[AdminOrderPaymentItem]


@router.get("", response_model=list[AdminOrderListItem])
async def list_orders(
    session: SessionDep,
    _admin: CurrentSuperUser,
    skip: int = 0,
    limit: int = 100,
) -> list[AdminOrderListItem]:
    """List customer orders (most recent first) with client and status names."""
    statement = (
        select(Order).order_by(col(Order.created_at).desc()).offset(skip).limit(limit)
    )
    result = await session.exec(statement)
    orders = list(result.all())

    user_ids = {o.user_id for o in orders}
    status_ids = {o.order_status_id for o in orders if o.order_status_id}

    users_by_id: dict[uuid.UUID, User] = {}
    if user_ids:
        users_res = await session.exec(select(User).where(col(User.id).in_(user_ids)))
        users_by_id = {u.id: u for u in users_res.all()}

    status_by_id: dict[uuid.UUID, str] = {}
    if status_ids:
        statuses_res = await session.exec(
            select(OrderStatus).where(col(OrderStatus.id).in_(status_ids))
        )
        status_by_id = {s.id: s.name for s in statuses_res.all()}

    items: list[AdminOrderListItem] = []
    for o in orders:
        user = users_by_id.get(o.user_id)
        items.append(
            AdminOrderListItem(
                order_id=o.id,
                created_at=o.created_at,
                user_id=o.user_id,
                user_name=user.full_name if user else None,
                user_email=user.email if user else None,
                status=status_by_id.get(o.order_status_id),
                total_amount=float(o.total_amount),
            )
        )
    return items


@router.get("/{order_id}", response_model=AdminOrderDetail)
async def get_order_detail(
    order_id: uuid.UUID,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> AdminOrderDetail:
    """Return the enriched detail of one order: client, status, lines, payments."""
    try:
        order = await crud_order.read(session, id=order_id)
    except RecordNotFoundError as exc:
        raise AppError(
            code="order.not_found",
            status_code=404,
            message=f"Order '{order_id}' not found",
            details={"order_id": str(order_id)},
        ) from exc

    # Client
    user_result = await session.exec(select(User).where(col(User.id) == order.user_id))
    user = user_result.first()

    # Status name
    status_name: str | None = None
    if order.order_status_id:
        status_result = await session.exec(
            select(OrderStatus).where(col(OrderStatus.id) == order.order_status_id)
        )
        status_record = status_result.first()
        status_name = status_record.name if status_record else None

    # Lines (+ product names)
    lines = await crud_order_line.get_by_order(session, order_id)
    product_ids = {line.product_id for line in lines}
    products_by_id: dict[uuid.UUID, Product] = {}
    if product_ids:
        products_res = await session.exec(
            select(Product).where(col(Product.id).in_(product_ids))
        )
        products_by_id = {p.id: p for p in products_res.all()}

    line_items = [
        AdminOrderLineItem(
            product_id=line.product_id,
            product_name=(
                products_by_id[line.product_id].name
                if line.product_id in products_by_id
                else None
            ),
            quantity=line.quantity,
            unit_price=float(line.unit_price),
            line_total=float(line.unit_price * line.quantity - line.discount_amount),
        )
        for line in lines
    ]

    # Payments (all of them — legacy orders may carry more than one)
    payments_result = await session.exec(
        select(Payment)
        .where(col(Payment.order_id) == order_id, col(Payment.is_active).is_(True))
        .order_by(col(Payment.created_at).asc())
    )
    payments = list(payments_result.all())
    pstatus_ids = {p.payment_status_id for p in payments if p.payment_status_id}
    pstatus_by_id: dict[uuid.UUID, str] = {}
    if pstatus_ids:
        pstatus_res = await session.exec(
            select(PaymentStatus).where(col(PaymentStatus.id).in_(pstatus_ids))
        )
        pstatus_by_id = {s.id: s.name for s in pstatus_res.all()}

    payment_items = []
    for p in payments:
        status_name = (
            pstatus_by_id.get(p.payment_status_id) if p.payment_status_id else None
        )
        payment_items.append(
            AdminOrderPaymentItem(
                payment_id=p.id,
                provider_code=p.provider_code,
                provider_reference=p.provider_reference,
                amount=float(p.amount),
                currency=p.currency,
                status=status_name,
                created_at=p.created_at,
                can_refund=(
                    provider_supports_in_app_refund(p.provider_code)
                    and status_name in _REFUNDABLE_PAYMENT_STATUSES
                ),
            )
        )

    return AdminOrderDetail(
        order_id=order.id,
        created_at=order.created_at,
        user_id=order.user_id,
        user_name=user.full_name if user else None,
        user_email=user.email if user else None,
        status=status_name,
        subtotal_amount=float(order.subtotal_amount),
        shipping_fee_amount=float(order.shipping_fee_amount),
        payment_fee_amount=float(order.payment_fee_amount),
        total_fees_amount=float(order.total_fees_amount),
        total_amount=float(order.total_amount),
        shipping_address=order.shipping_address,
        notes=order.notes,
        lines=line_items,
        payments=payment_items,
    )
