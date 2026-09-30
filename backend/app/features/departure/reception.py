"""Goods receipt of a grouped departure and its margin dashboard.

The admin tallies what arrived, product by product (« Réception » section of
the departure): received, damaged, serial numbers. Expected quantities are
never stored — they are the order lines of the attached orders. Received
units are matched to the orders first-come first-served (order date), which
gives each order a fulfilment status and each order line its serial numbers.

Nothing here commits; the endpoints own the transaction.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel
from sqlalchemy import func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.departure.crud import utcnow
from app.features.departure.models import (
    DepartureReceiptLine,
    GroupedDeparture,
    ReceiptLineWrite,
)
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.status import DEPARTURE_FOLLOWER_STATUSES
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.refund import Refund
from app.features.product.models.product import Product
from app.features.product.services.pricing import (
    CurrencyRateMissing,
    convert_to_reference_currency,
)

#: Orders whose goods travel with the departure (paid, on the way, or handed
#: over): the ones the receipt is matched against.
RECEIVABLE_STATUSES: frozenset[str] = DEPARTURE_FOLLOWER_STATUSES | {
    "ReadyForPickup",
    "Delivered",
}
#: Payments that count as money collected (a refund is deducted separately).
_COLLECTED_PAYMENT_STATUSES: tuple[str, ...] = (
    "Completed",
    "PartiallyRefunded",
    "Refunded",
)


# --- Views ------------------------------------------------------------------


class ReceiptLineView(BaseModel):
    """One product of the shipment: what was expected, what came in."""

    product_id: uuid.UUID
    product_name: str
    supplier_sku: str | None
    expected_quantity: int
    quantity_received: int = 0
    quantity_damaged: int = 0
    serial_numbers: list[str] = []
    notes: str | None = None
    received_at: datetime | None = None

    @property
    def good_quantity(self) -> int:
        return max(0, self.quantity_received - self.quantity_damaged)

    @property
    def missing_quantity(self) -> int:
        return max(0, self.expected_quantity - self.good_quantity)


class OrderLineAllocation(BaseModel):
    """Represents order line allocation."""

    product_id: uuid.UUID
    product_name: str
    quantity: int
    allocated: int
    serial_numbers: list[str] = []


class OrderReconciliation(BaseModel):
    """served: every unit is in; partial: some; unserved: nothing yet."""

    order_id: uuid.UUID
    order_number: str | None
    status: str | None
    fulfilment: str
    lines: list[OrderLineAllocation]


class ReceiptReport(BaseModel):
    """The « Réception » section: tally per product + orders reconciliation."""

    departure_id: uuid.UUID
    lines: list[ReceiptLineView]
    orders: list[OrderReconciliation]
    expected_units: int
    received_units: int
    damaged_units: int
    missing_units: int


class DepartureDashboard(BaseModel):
    """Money view of a departure (XPF)."""

    departure_id: uuid.UUID
    orders_count: int
    units: int
    revenue: Decimal
    collected: Decimal
    goods_cost_estimated: Decimal
    supplier_paid: Decimal
    unconverted_currencies: list[str]
    goods_cost_source: str
    freight_cost: Decimal
    customs_cost: Decimal
    other_costs: Decimal
    gross_margin: Decimal
    margin_rate_pct: Decimal | None


# --- Queries ----------------------------------------------------------------


async def _receivable_lines(
    session: AsyncSession, departure_id: uuid.UUID
) -> list[tuple[Order, str, OrderLine, Product]]:
    """Order lines of the orders travelling with the departure, oldest order
    first (the matching order)."""
    rows = (
        await session.exec(
            select(Order, col(OrderStatus.name), OrderLine, Product)
            .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
            .join(OrderLine, col(OrderLine.order_id) == col(Order.id))
            .join(Product, col(Product.id) == col(OrderLine.product_id))
            .where(
                col(Order.grouped_departure_id) == departure_id,
                col(Order.is_active).is_(True),
                col(OrderLine.is_active).is_(True),
                col(OrderStatus.name).in_(RECEIVABLE_STATUSES),
            )
            .order_by(col(Order.created_at).asc(), col(Order.id), col(OrderLine.id))
        )
    ).all()
    return [(order, name, line, product) for order, name, line, product in rows]


async def _receipt_lines(
    session: AsyncSession, departure_id: uuid.UUID
) -> dict[uuid.UUID, DepartureReceiptLine]:
    rows = (
        await session.exec(
            select(DepartureReceiptLine).where(
                col(DepartureReceiptLine.grouped_departure_id) == departure_id,
                col(DepartureReceiptLine.is_active).is_(True),
            )
        )
    ).all()
    return {r.product_id: r for r in rows}


# --- Reconciliation ---------------------------------------------------------


async def reconcile(
    session: AsyncSession, departure: GroupedDeparture, *, write_serials: bool = False
) -> ReceiptReport:
    """Match the received units to the order lines, oldest order first.

    With ``write_serials`` the serial numbers of the tally are copied onto the
    order lines in the same order (the customer sees them), for the products
    that have a tally.
    """
    rows = await _receivable_lines(session, departure.id)
    tallies = await _receipt_lines(session, departure.id)

    views: dict[uuid.UUID, ReceiptLineView] = {}
    for _order, _status, line, product in rows:
        view = views.get(product.id)
        if view is None:
            view = ReceiptLineView(
                product_id=product.id,
                product_name=product.name,
                supplier_sku=product.supplier_sku,
                expected_quantity=0,
            )
            tally = tallies.get(product.id)
            if tally is not None:
                view.quantity_received = tally.quantity_received
                view.quantity_damaged = tally.quantity_damaged
                view.serial_numbers = list(tally.serial_numbers or [])
                view.notes = tally.notes
                view.received_at = tally.received_at
            views[product.id] = view
        view.expected_quantity += int(line.quantity)

    remaining = {pid: v.good_quantity for pid, v in views.items()}
    serial_cursor = dict.fromkeys(views, 0)
    orders: dict[uuid.UUID, OrderReconciliation] = {}
    for order, status_name, line, product in rows:
        take = min(int(line.quantity), remaining[product.id])
        remaining[product.id] -= take
        serials: list[str] = []
        if product.id in tallies:
            start = serial_cursor[product.id]
            serials = views[product.id].serial_numbers[start : start + take]
            serial_cursor[product.id] = start + take
            if write_serials and (line.serial_numbers or None) != (serials or None):
                line.serial_numbers = serials or None
                session.add(line)
        elif line.serial_numbers:
            serials = list(line.serial_numbers)
        rec = orders.get(order.id)
        if rec is None:
            rec = OrderReconciliation(
                order_id=order.id,
                order_number=order.order_number,
                status=status_name,
                fulfilment="unserved",
                lines=[],
            )
            orders[order.id] = rec
        rec.lines.append(
            OrderLineAllocation(
                product_id=product.id,
                product_name=product.name,
                quantity=int(line.quantity),
                allocated=take,
                serial_numbers=serials,
            )
        )
    for rec in orders.values():
        allocated = sum(ln.allocated for ln in rec.lines)
        wanted = sum(ln.quantity for ln in rec.lines)
        rec.fulfilment = (
            "served" if allocated == wanted else "partial" if allocated else "unserved"
        )

    lines = sorted(views.values(), key=lambda v: (v.supplier_sku or "", v.product_name))
    return ReceiptReport(
        departure_id=departure.id,
        lines=lines,
        orders=list(orders.values()),
        expected_units=sum(v.expected_quantity for v in lines),
        received_units=sum(v.quantity_received for v in lines),
        damaged_units=sum(v.quantity_damaged for v in lines),
        missing_units=sum(v.missing_quantity for v in lines),
    )


async def upsert_receipt_line(
    session: AsyncSession,
    departure: GroupedDeparture,
    *,
    product_id: uuid.UUID,
    data: ReceiptLineWrite,
) -> DepartureReceiptLine:
    """Record (or correct) the tally of one product; flushes, no commit."""
    tallies = await _receipt_lines(session, departure.id)
    line = tallies.get(product_id) or DepartureReceiptLine(
        grouped_departure_id=departure.id, product_id=product_id
    )
    for key, value in data.model_dump().items():
        setattr(line, key, value)
    line.received_at = data.received_at or line.received_at or utcnow()
    session.add(line)
    await session.flush()
    return line


# --- Dashboard --------------------------------------------------------------


async def _collected(session: AsyncSession, order_ids: list[uuid.UUID]) -> Decimal:
    """Σ captured payments − Σ completed refunds on these orders."""
    if not order_ids:
        return Decimal(0)
    paid = (
        await session.exec(
            select(func.coalesce(func.sum(col(Payment.amount)), 0))
            .join(
                PaymentStatus, col(PaymentStatus.id) == col(Payment.payment_status_id)
            )
            .where(
                col(Payment.order_id).in_(order_ids),
                col(PaymentStatus.name).in_(_COLLECTED_PAYMENT_STATUSES),
            )
        )
    ).one()
    refunded = (
        await session.exec(
            select(func.coalesce(func.sum(col(Refund.amount)), 0)).where(
                col(Refund.order_id).in_(order_ids),
                col(Refund.status) == "completed",
            )
        )
    ).one()
    return Decimal(paid) - Decimal(refunded)


async def _supplier_paid(
    session: AsyncSession, departure: GroupedDeparture
) -> tuple[Decimal, list[str]]:
    """Σ recorded purchase orders in XPF; currencies without a rate are
    reported instead of silently skipped."""
    total = Decimal(0)
    unconverted: list[str] = []
    for entry in departure.supplier_orders or []:
        amount = Decimal(str(entry.get("total_amount") or 0))
        currency = str(entry.get("currency") or "XPF")
        try:
            converted, _rate = await convert_to_reference_currency(
                session, amount, currency
            )
        except CurrencyRateMissing:
            if currency not in unconverted:
                unconverted.append(currency)
            continue
        total += converted
    return total, unconverted


async def dashboard(
    session: AsyncSession, departure: GroupedDeparture
) -> DepartureDashboard:
    """Revenue, cash collected, goods cost (real when purchase orders are
    recorded, else the checkout cost snapshots), real shipment costs, margin."""
    rows = await _receivable_lines(session, departure.id)
    orders = {order.id: order for order, _s, _l, _p in rows}
    revenue = sum((o.total_amount for o in orders.values()), Decimal(0))
    units = sum(int(line.quantity) for _o, _s, line, _p in rows)
    estimated = Decimal(0)
    for _o, _s, line, _p in rows:
        if line.cost_amount_snapshot is not None:
            estimated += (
                line.cost_amount_snapshot
                * (line.fx_rate_used or Decimal(1))
                * int(line.quantity)
            )
    estimated = estimated.quantize(Decimal("0.01"))
    supplier_paid, unconverted = await _supplier_paid(session, departure)
    source = "supplier_orders" if departure.supplier_orders else "snapshots"
    goods_cost = supplier_paid if source == "supplier_orders" else estimated
    freight = departure.freight_cost or Decimal(0)
    customs = departure.customs_cost or Decimal(0)
    other = departure.other_costs or Decimal(0)
    margin = revenue - goods_cost - freight - customs - other
    return DepartureDashboard(
        departure_id=departure.id,
        orders_count=len(orders),
        units=units,
        revenue=revenue,
        collected=await _collected(session, list(orders)),
        goods_cost_estimated=estimated,
        supplier_paid=supplier_paid,
        unconverted_currencies=unconverted,
        goods_cost_source=source,
        freight_cost=freight,
        customs_cost=customs,
        other_costs=other,
        gross_margin=margin,
        margin_rate_pct=(
            (margin / revenue * 100).quantize(Decimal("0.1")) if revenue else None
        ),
    )


# --- Customer side ----------------------------------------------------------


def add_months(moment: datetime, months: int) -> datetime:
    """Calendar months later, clamped to the last day of the target month."""
    month_index = moment.month - 1 + months
    year, month = moment.year + month_index // 12, month_index % 12 + 1
    last_day = (
        datetime(year + (month == 12), month % 12 + 1, 1) - datetime(year, month, 1)
    ).days
    return moment.replace(year=year, month=month, day=min(moment.day, last_day))


class MyOrderLine(BaseModel):
    """An order line as the customer sees it: product, serials, warranty."""

    product_id: uuid.UUID
    product_name: str
    quantity: int
    unit_price: Decimal
    serial_numbers: list[str] = []
    warranty_months: int | None = None
    warranty_until: datetime | None = None


async def customer_lines(session: AsyncSession, order: Order) -> list[MyOrderLine]:
    """Lines of an order with the serial numbers handed over and the warranty
    end, counted from the day the goods were received."""
    rows = (
        await session.exec(
            select(OrderLine, Product)
            .join(Product, col(Product.id) == col(OrderLine.product_id))
            .where(
                col(OrderLine.order_id) == order.id,
                col(OrderLine.is_active).is_(True),
            )
            .order_by(col(OrderLine.id))
        )
    ).all()
    received: dict[uuid.UUID, datetime | None] = {}
    if order.grouped_departure_id:
        received = {
            pid: tally.received_at
            for pid, tally in (
                await _receipt_lines(session, order.grouped_departure_id)
            ).items()
        }
    items: list[MyOrderLine] = []
    for line, product in rows:
        since = received.get(product.id)
        items.append(
            MyOrderLine(
                product_id=product.id,
                product_name=product.name,
                quantity=int(line.quantity),
                unit_price=line.unit_price,
                serial_numbers=list(line.serial_numbers or []),
                warranty_months=product.warranty_months,
                warranty_until=(
                    add_months(since, product.warranty_months)
                    if since and product.warranty_months
                    else None
                ),
            )
        )
    return items


__all__ = [
    "RECEIVABLE_STATUSES",
    "DepartureDashboard",
    "MyOrderLine",
    "OrderReconciliation",
    "ReceiptLineView",
    "ReceiptReport",
    "add_months",
    "customer_lines",
    "dashboard",
    "reconcile",
    "upsert_receipt_line",
]
