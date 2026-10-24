"""Admin-facing client-order endpoints (superuser only).

Provides a list + rich detail view of customer orders for back-office use
(the payment-validation screen links here). The default CRUD `OrderPublic`
lacks client names, status names, lines and payments, so this module assembles
an enriched view.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy import select as sa_select
from sqlmodel import col, or_, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.api.routes.admin_payments import ReceiptResult, receipt_result
from app.core.datetimes import as_utc
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.order.crud.order_crud import crud_order
from app.features.order.crud.order_line_crud import crud_order_line
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.status import ALL_ORDER_STATUSES, set_order_status
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_receipt import PaymentReceiptPublic
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.providers import provider_supports_in_app_refund
from app.features.payment.providers.manual import MANUAL_STATUS_AWAITING_VALIDATION
from app.features.payment.services.deposit import PLAN_DEPOSIT, balance_amount
from app.features.payment.services.receipts import (
    next_part_due,
    order_payment_summary,
    received_by_payment,
    record_counter_payment,
)
from app.features.product.models.product import Product
from app.features.product.models.tax_rate import TaxRate
from app.features.product.services.margin import compute_margin, line_unit_cost
from app.features.product.services.pricing import PricingContext
from app.features.user.models.user import User
from app.handlers.order import request_balance
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


class AdminOrdersPage(BaseModel):
    """One page of the order list and the number of orders the filters match."""

    data: list[AdminOrderListItem]
    count: int


#: Columns the list may be sorted on (``sort_by``); anything else is refused.
ORDER_SORTS: dict[str, Any] = {
    "created_at": Order.created_at,
    "order_number": Order.order_number,
    "total_amount": Order.total_amount,
}


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
    #: Tax of the line (its snapshotted rate) and the line excl. tax.
    tax_rate_pct: float | None = None
    line_total_excl_tax: float | None = None
    #: Cost price of one unit at order time; None = cost unknown.
    unit_cost: float | None = None
    line_cost: float | None = None
    line_margin: float | None = None
    #: Margin / line excl. tax (taux de marque).
    margin_pct: float | None = None


class OrderMarginSummary(BaseModel):
    """Gross margin on the goods of an order (fees and shipping excluded)."""

    goods_excl_tax: float
    goods_cost: float
    margin: float
    margin_pct: float | None = None
    #: False when a line has no known cost: the figures cover the others only.
    complete: bool = True
    lines_without_cost: int = 0


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
    kind: str = "full"
    created_at: datetime | None = None
    # True when the admin UI may initiate a refund: the provider supports an
    # in-app refund (card / PayZen) and the payment is in a refundable state.
    can_refund: bool = False
    #: Σ of the instalments received so far on a pending manual payment.
    received_amount: float = 0.0
    #: The admin can record instalments on it (pending manual payment).
    accepts_receipts: bool = False


class AdminOrderDetail(BaseModel):
    """Represents the enriched admin order detail."""

    order_id: uuid.UUID
    order_number: str | None = None
    created_at: datetime | None = None
    user_id: uuid.UUID
    user_name: str | None = None
    user_email: str | None = None
    status: str | None = None
    subtotal_amount: float
    shipping_fee_amount: float
    payment_fee_amount: float
    total_fees_amount: float
    discount_code: str | None = None
    discount_amount: float = 0.0
    total_amount: float
    #: Currency of every amount of the order (frozen at checkout).
    currency: str | None = None
    shipping_address: str | None = None
    delivery_type: str | None = None
    grouped_departure_id: uuid.UUID | None = None
    notes: str | None = None
    # Deposit order (« acompte ») : plan, amounts and where the balance stands.
    payment_plan: str = "full"
    deposit_amount: float = 0.0
    deposit_fee_amount: float = 0.0
    balance_amount: float = 0.0
    balance_requested_at: datetime | None = None
    balance_paid_at: datetime | None = None
    lines: list[AdminOrderLineItem]
    #: Gross margin on the goods (None: no line has a known cost).
    margin: OrderMarginSummary | None = None
    payments: list[AdminOrderPaymentItem]
    #: Money in (settled payments + instalments − refunds) and what is left.
    amount_paid: float = 0.0
    amount_due: float = 0.0
    #: Every instalment received on the order's manual payments, oldest first.
    receipts: list[PaymentReceiptPublic] = []
    #: The part payable now (full / deposit / balance) and what is left of it:
    #: the default amount of « Enregistrer un encaissement ».
    next_part_kind: str | None = None
    next_part_due: float = 0.0


def _order_filters(
    statement: Any,
    *,
    departure_id: uuid.UUID | None,
    unassigned: bool,
    status: str | None,
    date_from: datetime | None,
    date_to: datetime | None,
    q: str | None = None,
) -> Any:
    """Shared WHERE clause of the list, the CSV export and the SKU summary.

    ``q`` searches the order number and the customer's name or e-mail.

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
        statement = statement.where(col(Order.created_at) >= as_utc(date_from))
    if date_to is not None:
        statement = statement.where(col(Order.created_at) <= as_utc(date_to))
    if q and q.strip():
        like = f"%{q.strip()}%"
        statement = statement.where(
            or_(
                col(Order.order_number).ilike(like),
                col(Order.user_id).in_(
                    select(User.id).where(
                        or_(
                            col(User.email).ilike(like), col(User.full_name).ilike(like)
                        )
                    )
                ),
            )
        )
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
    q: str | None = None,
    sort_by: str = "created_at",
    descending: bool = True,
) -> list[AdminOrderListItem]:
    sort_column = col(ORDER_SORTS[sort_by])
    statement = _order_filters(
        select(Order),
        departure_id=departure_id,
        unassigned=unassigned,
        status=status,
        date_from=date_from,
        date_to=date_to,
        q=q,
    ).order_by(
        sort_column.desc().nulls_last() if descending else sort_column.asc(),
        col(Order.id),
    )
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
_SearchQ = Query(
    default=None,
    max_length=120,
    description="Numéro de commande, nom ou e-mail du client (contient)",
)


@router.get("", response_model=AdminOrdersPage)
async def list_orders(
    session: SessionDep,
    _admin: CurrentSuperUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
    departure_id: uuid.UUID | None = _DepartureQ,
    unassigned: bool = _UnassignedQ,
    status: str | None = _StatusQ,
    date_from: datetime | None = _FromQ,
    date_to: datetime | None = _ToQ,
    q: str | None = _SearchQ,
    sort_by: str = Query(default="created_at"),
    descending: bool = Query(default=True),
) -> AdminOrdersPage:
    """One page of the customer orders with client and status names, and the
    number of orders the filters match (most recent first by default)."""
    if sort_by not in ORDER_SORTS:
        raise AppError(
            code="query.order_by_not_allowed",
            status_code=400,
            message="Tri non autorisé",
            details={"sort_by": sort_by, "allowed": sorted(ORDER_SORTS)},
        )
    filters: dict[str, Any] = {
        "departure_id": departure_id,
        "unassigned": unassigned,
        "status": status,
        "date_from": date_from,
        "date_to": date_to,
        "q": q,
    }
    count = (
        await session.exec(
            _order_filters(select(func.count()).select_from(Order), **filters)
        )
    ).one()
    data = await _list_order_rows(
        session,
        **filters,
        skip=skip,
        limit=limit,
        sort_by=sort_by,
        descending=descending,
    )
    return AdminOrdersPage(data=data, count=int(count))


@router.get("/export.csv")
async def export_orders_csv(
    session: SessionDep,
    _admin: CurrentSuperUser,
    departure_id: uuid.UUID | None = _DepartureQ,
    unassigned: bool = _UnassignedQ,
    status: str | None = _StatusQ,
    date_from: datetime | None = _FromQ,
    date_to: datetime | None = _ToQ,
    q: str | None = _SearchQ,
) -> Response:
    """Raw export of the filtered orders (one row per order)."""
    rows = await _list_order_rows(
        session,
        departure_id=departure_id,
        unassigned=unassigned,
        status=status,
        date_from=date_from,
        date_to=date_to,
        q=q,
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


class OrderStatusChangeRequest(BaseModel):
    """Represents order status change request."""

    status: str
    reason: str | None = None


class OrderStatusChangeResponse(BaseModel):
    """Represents order status change response."""

    order_id: uuid.UUID
    status: str
    changed: bool


@router.get("/statuses", response_model=list[str])
async def list_order_statuses(_admin: CurrentSuperUser) -> list[str]:
    """Every order status name, payment ones first then the fulfilment steps."""
    return list(ALL_ORDER_STATUSES)


@router.post("/{order_id}/status", response_model=OrderStatusChangeResponse)
async def change_order_status(
    order_id: uuid.UUID,
    body: OrderStatusChangeRequest,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> OrderStatusChangeResponse:
    """Move one order to a status by hand (the bulk path is the departure)."""
    if body.status not in ALL_ORDER_STATUSES:
        raise AppError(
            code="order.status.unknown",
            status_code=400,
            message=f"Statut inconnu '{body.status}'",
            details={"status": body.status, "known": list(ALL_ORDER_STATUSES)},
        )
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError(
            code="order.not_found",
            status_code=404,
            message="Commande introuvable",
            details={"order_id": str(order_id)},
        )
    changed = await set_order_status(
        session,
        order=order,
        status_name=body.status,
        changed_by_id=admin.id,
        reason=body.reason,
    )
    await session.commit()
    return OrderStatusChangeResponse(
        order_id=order_id, status=body.status, changed=changed
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

    tax_ids = {line.tax_rate_id for line in lines if line.tax_rate_id}
    tax_pct_by_id: dict[uuid.UUID, Decimal] = {}
    if tax_ids:
        tax_res = await session.exec(
            select(TaxRate).where(col(TaxRate.id).in_(tax_ids))
        )
        tax_pct_by_id = {r.id: Decimal(r.rate_pct) for r in tax_res.all()}

    # Same commission as the product margin (grossed into the price).
    try:
        commission_pct: Decimal | None = (
            await PricingContext.for_session(session)
        ).payment_commission_pct
    except Exception:  # noqa: BLE001 - a missing parameter never hides an order
        commission_pct = None

    line_items: list[AdminOrderLineItem] = []
    margin_totals = {"excl": Decimal("0"), "cost": Decimal("0"), "fees": Decimal("0")}
    lines_without_cost = 0
    for line in lines:
        total = line.unit_price * line.quantity - line.discount_amount
        tax_pct = tax_pct_by_id.get(line.tax_rate_id) if line.tax_rate_id else None
        unit_cost = line_unit_cost(line)
        figures = compute_margin(
            price_incl_tax=total,
            tax_rate_pct=tax_pct,
            unit_cost=unit_cost * line.quantity if unit_cost is not None else None,
            commission_pct=commission_pct,
        )
        if figures is None:
            lines_without_cost += 1
        else:
            margin_totals["excl"] += figures.price_excl_tax
            margin_totals["cost"] += figures.unit_cost
            margin_totals["fees"] += figures.commission_amount
        line_items.append(
            AdminOrderLineItem(
                product_id=line.product_id,
                product_name=(
                    products_by_id[line.product_id].name
                    if line.product_id in products_by_id
                    else None
                ),
                quantity=line.quantity,
                unit_price=float(line.unit_price),
                line_total=float(total),
                tax_rate_pct=float(tax_pct) if tax_pct is not None else None,
                line_total_excl_tax=(
                    float(figures.price_excl_tax) if figures is not None else None
                ),
                unit_cost=float(unit_cost) if unit_cost is not None else None,
                line_cost=float(figures.unit_cost) if figures is not None else None,
                line_margin=(
                    float(figures.margin_amount) if figures is not None else None
                ),
                margin_pct=(
                    float(figures.margin_pct)
                    if figures is not None and figures.margin_pct is not None
                    else None
                ),
            )
        )
    margin_summary: OrderMarginSummary | None = None
    if lines and lines_without_cost < len(lines):
        goods_margin = (
            margin_totals["excl"] - margin_totals["fees"] - margin_totals["cost"]
        )
        margin_summary = OrderMarginSummary(
            goods_excl_tax=float(margin_totals["excl"]),
            goods_cost=float(margin_totals["cost"]),
            margin=float(goods_margin),
            margin_pct=(
                float(round(goods_margin / margin_totals["excl"] * 100, 2))
                if margin_totals["excl"] > 0
                else None
            ),
            complete=lines_without_cost == 0,
            lines_without_cost=lines_without_cost,
        )

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
    summary = await order_payment_summary(session, order=order)
    part_kind, part_due = await next_part_due(session, order=order)
    received = await received_by_payment(session, [p.id for p in payments])
    for p in payments:
        payment_status_name = (
            pstatus_by_id.get(p.payment_status_id) if p.payment_status_id else None
        )
        payment_items.append(
            AdminOrderPaymentItem(
                payment_id=p.id,
                provider_code=p.provider_code,
                provider_reference=p.provider_reference,
                amount=float(p.amount),
                currency=p.currency,
                status=payment_status_name,
                kind=p.kind,
                created_at=p.created_at,
                can_refund=(
                    provider_supports_in_app_refund(p.provider_code)
                    and payment_status_name in _REFUNDABLE_PAYMENT_STATUSES
                ),
                received_amount=float(received.get(p.id, 0)),
                accepts_receipts=(
                    (p.provider_code or "").startswith("manual_")
                    and payment_status_name == MANUAL_STATUS_AWAITING_VALIDATION
                ),
            )
        )

    return AdminOrderDetail(
        order_id=order.id,
        order_number=order.order_number,
        created_at=order.created_at,
        user_id=order.user_id,
        user_name=user.full_name if user else None,
        user_email=user.email if user else None,
        status=status_name,
        currency=getattr(order, "currency", None),
        subtotal_amount=float(order.subtotal_amount),
        shipping_fee_amount=float(order.shipping_fee_amount),
        payment_fee_amount=float(order.payment_fee_amount),
        total_fees_amount=float(order.total_fees_amount),
        discount_code=getattr(order, "discount_code", None),
        discount_amount=float(getattr(order, "discount_amount", None) or 0),
        total_amount=float(order.total_amount),
        shipping_address=order.shipping_address,
        delivery_type=getattr(order, "delivery_type", None),
        grouped_departure_id=order.grouped_departure_id,
        notes=order.notes,
        payment_plan=order.payment_plan,
        deposit_amount=float(order.deposit_amount),
        deposit_fee_amount=float(order.deposit_fee_amount),
        balance_amount=float(balance_amount(order)),
        balance_requested_at=order.balance_requested_at,
        balance_paid_at=order.balance_paid_at,
        lines=line_items,
        margin=margin_summary,
        payments=payment_items,
        amount_paid=float(summary.paid),
        amount_due=float(summary.due),
        next_part_kind=part_kind,
        next_part_due=float(part_due),
        receipts=[
            PaymentReceiptPublic.model_validate(r, from_attributes=True)
            for r in summary.receipts
        ],
    )


class CounterPaymentCreate(BaseModel):
    """Money handed over at the office for the part of the order now due."""

    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    method: str = Field(description="cash | check | transfer")
    received_at: datetime | None = None
    reference: str | None = Field(default=None, max_length=100)
    note: str | None = Field(default=None, max_length=500)


@router.post("/{order_id}/payments", response_model=ReceiptResult)
async def record_order_counter_payment(
    order_id: uuid.UUID,
    body: CounterPaymentCreate,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> ReceiptResult:
    """« Enregistrer un encaissement » : cash, cheque or transfer received for
    the part now due, on the customer's pending manual payment or a new one."""
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError(
            code="order.not_found",
            status_code=404,
            message="Commande introuvable",
            details={"order_id": str(order_id)},
        )
    try:
        outcome = await record_counter_payment(
            session,
            order=order,
            admin=admin,
            amount=body.amount,
            method=body.method,
            received_at=body.received_at,
            reference=body.reference,
            note=body.note,
        )
        result = receipt_result(outcome)
        await session.commit()
    except AppError:
        await session.rollback()
        raise
    return result


class RequestBalanceResponse(BaseModel):
    """Represents request balance response."""

    order_id: uuid.UUID
    balance_amount: float
    sent: bool


@router.post("/{order_id}/request-balance", response_model=RequestBalanceResponse)
async def request_order_balance(
    order_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> RequestBalanceResponse:
    """Send (or re-send) the balance request e-mail of a deposit order — the
    automatic one goes out when the order is received."""
    order = await session.get(Order, order_id)
    if order is None:
        raise AppError(
            code="order.not_found",
            status_code=404,
            message="Commande introuvable",
            details={"order_id": str(order_id)},
        )
    due = balance_amount(order)
    if order.payment_plan != PLAN_DEPOSIT or order.balance_paid_at is not None:
        raise AppError(
            code="order.balance.not_due",
            status_code=409,
            message="Aucun solde à demander sur cette commande",
            details={"order_id": str(order_id), "payment_plan": order.payment_plan},
        )
    sent = await request_balance(session, order)
    await session.commit()
    return RequestBalanceResponse(
        order_id=order_id, balance_amount=float(due), sent=sent
    )
