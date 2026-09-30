"""Integration tests (real DB): goods receipt of a departure (tally per
product, first-come first-served reconciliation, serial numbers handed to
the order lines and shown to the customer with the warranty end), and the
margin dashboard (revenue, cash collected, goods cost, real costs)."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_grouped_departures import (
    add_supplier_order,
    get_dashboard,
    get_reception,
    put_reception_line,
    update_departure,
)
from app.api.routes.orders_me import get_my_order_lines
from app.core.errors import AppError
from app.features.departure.models import (
    GroupedDeparture,
    GroupedDepartureUpdate,
    ReceiptLineWrite,
    SupplierOrderEntry,
)
from app.features.departure.reception import add_months
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.payment.models.refund import Refund
from app.features.product.models.product import Product
from app.features.user.models.user import User

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


async def _seed(session: AsyncSession) -> SimpleNamespace:
    """Two paid orders (2 + 3 laptops, 1 mouse) and one pending order on a
    departure; one card payment per paid order, a refund on the second."""
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    paid, pending = OrderStatus(name="Paid"), OrderStatus(name="Pending")
    completed = PaymentStatus(name="Completed")
    laptop = Product(
        name="Laptop",
        supplier_name="ingram_micro",
        supplier_sku="LT-1",
        warranty_months=12,
    )
    mouse = Product(name="Souris", supplier_name="local", supplier_sku="MS-1")
    departure = GroupedDeparture(
        name="Octobre",
        order_cutoff_at=NOW + timedelta(days=10),
        status="received",
        freight_cost=Decimal("300"),
    )
    session.add_all([admin, buyer, paid, pending, completed, laptop, mouse, departure])
    await session.flush()

    def order(status: OrderStatus, total: str, day: int) -> Order:
        return Order(
            user_id=buyer.id,
            order_status_id=status.id,
            order_number=f"CMD-{uuid.uuid4().hex[:6]}",
            total_amount=Decimal(total),
            grouped_departure_id=departure.id,
            created_at=datetime(2026, 9, day, 10, 0, tzinfo=timezone.utc),
        )

    o1, o2, o3 = order(paid, "1000", 1), order(paid, "2000", 2), order(pending, "50", 3)
    session.add_all([o1, o2, o3])
    await session.flush()
    session.add_all(
        [
            OrderLine(
                order_id=o1.id,
                product_id=laptop.id,
                quantity=2,
                unit_price=Decimal(500),
                cost_amount_snapshot=Decimal("2.5"),
                cost_currency_snapshot="EUR",
                fx_rate_used=Decimal("120"),
            ),
            OrderLine(
                order_id=o2.id,
                product_id=laptop.id,
                quantity=3,
                unit_price=Decimal(500),
                cost_amount_snapshot=Decimal("2.5"),
                cost_currency_snapshot="EUR",
                fx_rate_used=Decimal("120"),
            ),
            OrderLine(
                order_id=o2.id, product_id=mouse.id, quantity=1, unit_price=Decimal(10)
            ),
            Payment(
                order_id=o1.id,
                user_id=buyer.id,
                amount=Decimal(1000),
                payment_status_id=completed.id,
            ),
            Payment(
                order_id=o2.id,
                user_id=buyer.id,
                amount=Decimal(2000),
                payment_status_id=completed.id,
            ),
        ]
    )
    await session.flush()
    refund_payment = (
        await session.exec(select(Payment).where(col(Payment.order_id) == o2.id))
    ).one()
    session.add(
        Refund(
            payment_id=refund_payment.id,
            order_id=o2.id,
            amount=Decimal(100),
            status="completed",
        )
    )
    await session.flush()
    return SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        buyer=cast(User, SimpleNamespace(id=buyer.id)),
        departure_id=departure.id,
        laptop_id=laptop.id,
        mouse_id=mouse.id,
        first_id=o1.id,
        second_id=o2.id,
        pending_id=o3.id,
    )


@pytest.mark.asyncio
async def test_receipt_tally_reconciles_orders_and_hands_serials_to_lines(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    # Before anything arrives: expected from the paid orders only.
    report = await get_reception(seed.departure_id, db_session, seed.admin)
    by_sku = {ln.supplier_sku: ln for ln in report.lines}
    assert (
        by_sku["LT-1"].expected_quantity == 5 and by_sku["MS-1"].expected_quantity == 1
    )
    assert (report.expected_units, report.received_units, report.missing_units) == (
        6,
        0,
        6,
    )
    assert {o.fulfilment for o in report.orders} == {"unserved"}
    assert {o.order_id for o in report.orders} == {seed.first_id, seed.second_id}

    # 4 laptops arrive, one of them damaged: the oldest order is served first.
    report = await put_reception_line(
        seed.departure_id,
        seed.laptop_id,
        ReceiptLineWrite(
            quantity_received=4,
            quantity_damaged=1,
            serial_numbers=["SN-A", "SN-B ", "SN-C"],
            received_at=NOW,
        ),
        db_session,
        seed.admin,
    )
    laptop = next(ln for ln in report.lines if ln.supplier_sku == "LT-1")
    assert (laptop.quantity_received, laptop.quantity_damaged) == (4, 1)
    assert laptop.missing_quantity == 2  # 5 expected, 3 good
    assert laptop.serial_numbers == ["SN-A", "SN-B", "SN-C"]
    fulfilment = {o.order_id: o for o in report.orders}
    assert fulfilment[seed.first_id].fulfilment == "served"
    assert fulfilment[seed.first_id].lines[0].serial_numbers == ["SN-A", "SN-B"]
    second = fulfilment[seed.second_id]
    assert second.fulfilment == "partial"
    assert {ln.product_id: ln.allocated for ln in second.lines} == {
        seed.laptop_id: 1,
        seed.mouse_id: 0,
    }

    # The serial numbers are on the order lines, and the customer sees them
    # with the warranty end (12 months from the receipt).
    lines = await get_my_order_lines(seed.first_id, db_session, seed.buyer)
    assert lines[0].serial_numbers == ["SN-A", "SN-B"]
    assert lines[0].warranty_months == 12
    assert lines[0].warranty_until == add_months(NOW, 12)
    mine = await get_my_order_lines(seed.second_id, db_session, seed.buyer)
    by_product = {ln.product_id: ln for ln in mine}
    assert by_product[seed.laptop_id].serial_numbers == ["SN-C"]
    assert by_product[seed.mouse_id].serial_numbers == []
    assert by_product[seed.mouse_id].warranty_until is None
    with pytest.raises(AppError) as denied:
        await get_my_order_lines(seed.first_id, db_session, seed.admin)
    assert denied.value.code == "order.not_owned"

    # Correcting the tally re-allocates (idempotent): the mouse arrives, the
    # fifth laptop too → the second order is served.
    await put_reception_line(
        seed.departure_id,
        seed.mouse_id,
        ReceiptLineWrite(quantity_received=1),
        db_session,
        seed.admin,
    )
    report = await put_reception_line(
        seed.departure_id,
        seed.laptop_id,
        ReceiptLineWrite(
            quantity_received=5, serial_numbers=["SN-A", "SN-B", "SN-C", "SN-D", "SN-E"]
        ),
        db_session,
        seed.admin,
    )
    assert report.missing_units == 0
    assert {o.fulfilment for o in report.orders} == {"served"}
    mine = await get_my_order_lines(seed.second_id, db_session, seed.buyer)
    assert {ln.product_id: ln.serial_numbers for ln in mine} == {
        seed.laptop_id: ["SN-C", "SN-D", "SN-E"],
        seed.mouse_id: [],
    }

    # Duplicated serial numbers are refused at the schema level.
    with pytest.raises(ValueError):
        ReceiptLineWrite(quantity_received=2, serial_numbers=["X", "X"])


@pytest.mark.asyncio
async def test_dashboard_uses_snapshots_then_the_real_purchase_orders(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    board = await get_dashboard(seed.departure_id, db_session, seed.admin)
    assert (board.orders_count, board.units) == (2, 6)
    assert board.revenue == Decimal("3000")
    assert board.collected == Decimal("2900")  # 3000 paid − 100 refunded
    # 5 laptops × 2.5 EUR × 120 = 1500 XPF; the mouse has no cost snapshot.
    assert board.goods_cost_estimated == Decimal("1500.00")
    assert board.goods_cost_source == "snapshots"
    assert board.freight_cost == Decimal("300")
    assert board.gross_margin == Decimal("1200.00")
    assert board.margin_rate_pct == Decimal("40.0")

    # A purchase order in XPF and the real customs typed on the departure.
    await add_supplier_order(
        seed.departure_id,
        SupplierOrderEntry(
            supplier_name="ingram_micro",
            order_number="IM-1",
            ordered_at=NOW,
            total_amount=Decimal("1700"),
            currency="XPF",
        ),
        db_session,
        seed.admin,
    )
    await update_departure(
        seed.departure_id,
        GroupedDepartureUpdate(customs_cost=Decimal("200")),
        db_session,
        seed.admin,
    )
    board = await get_dashboard(seed.departure_id, db_session, seed.admin)
    assert board.goods_cost_source == "supplier_orders"
    assert board.supplier_paid == Decimal("1700")
    assert board.gross_margin == Decimal("800")  # 3000 − 1700 − 300 − 200
    assert board.margin_rate_pct == Decimal("26.7")

    # A purchase order in a currency without a rate is reported, not summed.
    await add_supplier_order(
        seed.departure_id,
        SupplierOrderEntry(
            supplier_name="other",
            order_number="X-1",
            ordered_at=NOW,
            total_amount=Decimal("10"),
            currency="ZZZ",
        ),
        db_session,
        seed.admin,
    )
    board = await get_dashboard(seed.departure_id, db_session, seed.admin)
    assert board.unconverted_currencies == ["ZZZ"]
    assert board.supplier_paid == Decimal("1700")


def test_add_months_clamps_to_the_end_of_month() -> None:
    assert add_months(datetime(2026, 1, 31), 1) == datetime(2026, 2, 28)
    assert add_months(datetime(2026, 11, 15), 2) == datetime(2027, 1, 15)
    assert add_months(datetime(2026, 12, 31, tzinfo=timezone.utc), 24) == datetime(
        2028, 12, 31, tzinfo=timezone.utc
    )
