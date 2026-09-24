"""Admin-facing client-order endpoints (superuser only).

Provides a list + rich detail view of customer orders for back-office use
(the payment-validation screen links here). The default CRUD `OrderPublic`
lacks client names, status names, lines and payments, so this module assembles
an enriched view.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.providers import provider_supports_in_app_refund
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.utils.csv_export import csv_amount, csv_response

router = APIRouter(prefix="/admin/orders", tags=["admin-order"])


class AdminOrderListItem(BaseModel):
    """Represents an admin order list row."""

    order_id: uuid.UUID
    order_number: str | None = None
    created_at: datetime | None = None
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    status: str | None = None
    total_amount: float
    currency: str | None = None
    grouped_departure_id: uuid.UUID | None = None


class SkuSummaryRow(BaseModel):
    """One supplier SKU aggregated over the filtered orders (= purchase order line)."""

    product_id: uuid.UUID
    supplier_name: str | None = None
    supplier_sku: str | None = None
    vendor_part_number: str | None = None
    product_name: str
    quantity: int
    orders_count: int
    unit_cost: float | None = None
    cost_currency: str | None = None
    unit_weight_kg: float | None = None
    total_weight_kg: float | None = None


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
    delivery_type: str | None = None
    grouped_departure_id: uuid.UUID | None = None
    notes: str | None = None
    lines: list[AdminOrderLineItem]
    payments: list[AdminOrderPaymentItem]


def _order_filters(
    statement: Any,
    *,
    departure_id: uuid.UUID | None,
    unassigned: bool,
    status: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> Any:
    """Shared WHERE clause of the list, the CSV export and the SKU summary.

    ``departure_id`` and ``unassigned`` are the two ways to work a grouped
    departure (its orders, or the orders still to attach); the dates cover
    the manual mode (« export d'une période ») when no departure is used.
    """
    if departure_id is not None:
        statement = statement.where(Order.grouped_departure_id == departure_id)
    if unassigned:
        statement = statement.where(col(Order.grouped_departure_id).is_(None))
    if status:
        statement = statement.where(
            col(Order.order_status_id).in_(
                select(OrderStatus.id).where(OrderStatus.name == status)
            )
        )
    if date_from is not None:
        statement = statement.where(col(Order.created_at) >= date_from)
    if date_to is not None:
        statement = statement.where(col(Order.created_at) <= date_to)
    return statement


async def _list_order_rows(
    session: SessionDep,
    *,
    departure_id: uuid.UUID | None,
    unassigned: bool,
    status: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    skip: int,
    limit: int | None,
) -> list[AdminOrderListItem]:
    statement = _order_filters(
        select(Order),
        departure_id=departure_id,
        unassigned=unassigned,
        status=status,
        date_from=date_from,
        date_to=date_to,
    ).order_by(col(Order.created_at).desc())
    if limit is not None:
        statement = statement.offset(skip).limit(limit)
    orders = list((await session.exec(statement)).all())

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
                order_number=o.order_number,
                created_at=o.created_at,
                user_id=o.user_id,
                user_name=user.full_name if user else None,
                user_email=user.email if user else None,
                status=status_by_id.get(o.order_status_id),
                total_amount=float(o.total_amount),
                currency=o.currency,
                grouped_departure_id=o.grouped_departure_id,
            )
        )
    return items


# Query parameters shared by the three filtered endpoints.
_DepartureQ = Query(default=None, description="Commandes rattachées à ce départ groupé")
_UnassignedQ = Query(default=False, description="Commandes sans départ groupé")
_StatusQ = Query(default=None, description="Nom du statut de commande (ex. Paid)")
_FromQ = Query(default=None, description="Commandes créées à partir de cette date")
_ToQ = Query(default=None, description="Commandes créées jusqu'à cette date")


@router.get("", response_model=list[AdminOrderListItem])
async def list_orders(
    session: SessionDep,
    _admin: CurrentSuperUser,
    skip: int = 0,
    limit: int = 100,
    departure_id: uuid.UUID | None = _DepartureQ,
    unassigned: bool = _UnassignedQ,
    status: str | None = _StatusQ,
    date_from: datetime | None = _FromQ,
    date_to: datetime | None = _ToQ,
) -> list[AdminOrderListItem]:
    """List customer orders (most recent first) with client and status names."""
    return await _list_order_rows(
        session,
        departure_id=departure_id,
        unassigned=unassigned,
        status=status,
        date_from=date_from,
        date_to=date_to,
        skip=skip,
        limit=limit,
    )


@router.get("/export.csv")
async def export_orders_csv(
    session: SessionDep,
    _admin: CurrentSuperUser,
    departure_id: uuid.UUID | None = _DepartureQ,
    unassigned: bool = _UnassignedQ,
    status: str | None = _StatusQ,
    date_from: datetime | None = _FromQ,
    date_to: datetime | None = _ToQ,
) -> Response:
    """Raw export of the filtered orders (one row per order)."""
    rows = await _list_order_rows(
        session,
        departure_id=departure_id,
        unassigned=unassigned,
        status=status,
        date_from=date_from,
        date_to=date_to,
        skip=0,
        limit=None,
    )
    return csv_response(
        ["Numéro", "Date", "Client", "E-mail", "Statut", "Départ", "Devise", "Total"],
        (
            [
                r.order_number or str(r.order_id),
                r.created_at.date().isoformat() if r.created_at else "",
                r.user_name or "",
                r.user_email or "",
                r.status or "",
                str(r.grouped_departure_id) if r.grouped_departure_id else "",
                r.currency or "",
                csv_amount(r.total_amount),
            ]
            for r in rows
        ),
        filename="commandes.csv",
    )


async def _sku_summary_rows(
    session: SessionDep,
    *,
    departure_id: uuid.UUID | None,
    unassigned: bool,
    status: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
) -> list[SkuSummaryRow]:
    """Order lines of the filtered orders aggregated per product = the supplier
    purchase order (quantity, cost snapshot, weight) — item B9 of the spec."""
    statement = (
        _order_filters(
            # sqlalchemy.select: sqlmodel's typed select stops at four columns.
            sa_select(
                col(Product.id),
                col(Product.supplier_name),
                col(Product.supplier_sku),
                col(Product.vendor_part_number),
                col(Product.name),
                col(Product.weight),
                func.sum(col(OrderLine.quantity)),
                func.count(func.distinct(col(OrderLine.order_id))),
                func.avg(col(OrderLine.cost_amount_snapshot)),
                func.max(col(OrderLine.cost_currency_snapshot)),
            )
            .join(OrderLine, col(OrderLine.product_id) == col(Product.id))
            .join(Order, col(Order.id) == col(OrderLine.order_id))
            .where(col(OrderLine.is_active).is_(True)),
            departure_id=departure_id,
            unassigned=unassigned,
            status=status,
            date_from=date_from,
            date_to=date_to,
        )
        .group_by(
            Product.id,
            Product.supplier_name,
            Product.supplier_sku,
            Product.vendor_part_number,
            Product.name,
            Product.weight,
        )
        .order_by(Product.supplier_name, Product.supplier_sku, Product.name)
    )
    rows = (await session.execute(statement)).all()
    summary: list[SkuSummaryRow] = []
    for pid, supplier, sku, vpn, name, weight, qty, n_orders, cost, currency in rows:
        quantity = int(qty or 0)
        summary.append(
            SkuSummaryRow(
                product_id=pid,
                supplier_name=supplier,
                supplier_sku=sku,
                vendor_part_number=vpn,
                product_name=name,
                quantity=quantity,
                orders_count=int(n_orders or 0),
                unit_cost=float(cost) if cost is not None else None,
                cost_currency=currency,
                unit_weight_kg=weight,
                total_weight_kg=round(weight * quantity, 3) if weight else None,
            )
        )
    return summary


@router.get("/sku-summary", response_model=list[SkuSummaryRow])
async def sku_summary(
    session: SessionDep,
    _admin: CurrentSuperUser,
    departure_id: uuid.UUID | None = _DepartureQ,
    unassigned: bool = _UnassignedQ,
    status: str | None = _StatusQ,
    date_from: datetime | None = _FromQ,
    date_to: datetime | None = _ToQ,
) -> list[SkuSummaryRow]:
    """Filtered orders aggregated by supplier × SKU (the purchase order)."""
    return await _sku_summary_rows(
        session,
        departure_id=departure_id,
        unassigned=unassigned,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )


@router.get("/sku-summary.csv")
async def sku_summary_csv(
    session: SessionDep,
    _admin: CurrentSuperUser,
    departure_id: uuid.UUID | None = _DepartureQ,
    unassigned: bool = _UnassignedQ,
    status: str | None = _StatusQ,
    date_from: datetime | None = _FromQ,
    date_to: datetime | None = _ToQ,
) -> Response:
    """Same aggregation as ``/sku-summary``, as a downloadable CSV."""
    rows = await _sku_summary_rows(
        session,
        departure_id=departure_id,
        unassigned=unassigned,
        status=status,
        date_from=date_from,
        date_to=date_to,
    )
    return csv_response(
        [
            "Fournisseur",
            "SKU fournisseur",
            "Réf. fabricant",
            "Produit",
            "Quantité",
            "Commandes",
            "Coût unitaire",
            "Devise coût",
            "Poids unitaire (kg)",
            "Poids total (kg)",
        ],
        (
            [
                r.supplier_name or "",
                r.supplier_sku or "",
                r.vendor_part_number or "",
                r.product_name,
                r.quantity,
                r.orders_count,
                csv_amount(r.unit_cost),
                r.cost_currency or "",
                r.unit_weight_kg if r.unit_weight_kg is not None else "",
                r.total_weight_kg if r.total_weight_kg is not None else "",
            ]
            for r in rows
        ),
        filename="bon-de-commande-par-sku.csv",
    )


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
        delivery_type=getattr(order, "delivery_type", None),
        grouped_departure_id=order.grouped_departure_id,
        notes=order.notes,
        lines=line_items,
        payments=payment_items,
    )
