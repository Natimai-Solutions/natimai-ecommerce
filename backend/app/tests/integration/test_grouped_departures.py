"""Integration tests (real DB): grouped departures — resolver, admin endpoints,
order attachment, filtered order list / CSV / SKU summary, public endpoints."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_grouped_departures import (
    AssignOrdersRequest,
    assign_orders,
    create_departure,
    delete_departure,
    list_departures,
    update_departure,
)
from app.api.routes.admin_orders import (
    _list_order_rows,
    _sku_summary_rows,
    export_orders_csv,
    sku_summary_csv,
)
from app.api.routes.grouped_departures import get_departure, next_departure
from app.core.errors import AppError
from app.features.departure.crud import crud_grouped_departure
from app.features.departure.models import (
    GroupedDeparture,
    GroupedDepartureCreate,
    GroupedDepartureUpdate,
)
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.product import Product
from app.features.user.models.user import User

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


@pytest.fixture(autouse=True)
def _at_now(freeze_departure_clock: Callable[[datetime], None]) -> None:
    """Every test runs on NOW, the date its cutoffs are written from."""
    freeze_departure_clock(NOW)


def _departure(name: str, days: int, **overrides: Any) -> GroupedDeparture:
    fields: dict[str, Any] = {
        "name": name,
        "order_cutoff_at": NOW + timedelta(days=days),
        "status": "open",
        "is_published": True,
    }
    fields.update(overrides)
    return GroupedDeparture(**fields)


async def _seed(session: AsyncSession) -> SimpleNamespace:
    """A superuser, two customers, two products and three orders (two with lines)."""
    admin = User(
        email=f"admin+{uuid.uuid4().hex[:8]}@test.local",
        is_superuser=True,
        is_active=True,
        hashed_password="x",
    )
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        full_name="Tehani",
        is_active=True,
        hashed_password="x",
    )
    paid = OrderStatus(name="Paid")
    pending = OrderStatus(name="Pending")
    laptop = Product(
        name="Laptop", supplier_name="ingram", supplier_sku="LT-1", weight=2.5
    )
    mouse = Product(name="Souris", supplier_name="ingram", supplier_sku="MS-1")
    session.add_all([admin, buyer, paid, pending, laptop, mouse])
    await session.flush()

    def order(status: OrderStatus, day: int, total: str) -> Order:
        return Order(
            user_id=buyer.id,
            order_status_id=status.id,
            order_number=f"CMD-2026-{day:05d}",
            total_amount=Decimal(total),
            currency="XPF",
            created_at=datetime(2026, 10, day, 10, 0, tzinfo=UTC),
        )

    o1, o2, o3 = order(paid, 1, "1000"), order(paid, 5, "2000"), order(pending, 9, "50")
    session.add_all([o1, o2, o3])
    await session.flush()
    session.add_all(
        [
            OrderLine(
                order_id=o1.id,
                product_id=laptop.id,
                quantity=1,
                unit_price=Decimal("1000"),
                cost_amount_snapshot=Decimal("700"),
                cost_currency_snapshot="EUR",
            ),
            OrderLine(
                order_id=o2.id,
                product_id=laptop.id,
                quantity=2,
                unit_price=Decimal("1000"),
                cost_amount_snapshot=Decimal("800"),
                cost_currency_snapshot="EUR",
            ),
            OrderLine(
                order_id=o2.id,
                product_id=mouse.id,
                quantity=3,
                unit_price=Decimal("10"),
            ),
        ]
    )
    await session.flush()
    return SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        orders=[o1.id, o2.id, o3.id],
        laptop_id=laptop.id,
        mouse_id=mouse.id,
    )


def _filters(**overrides: Any) -> dict[str, Any]:
    base: dict[str, Any] = {
        "departure_id": None,
        "unassigned": False,
        "status": None,
        "date_from": None,
        "date_to": None,
    }
    base.update(overrides)
    return base


@pytest.mark.asyncio
async def test_next_open_departure_is_the_nearest_published_open_cutoff(
    db_session: AsyncSession,
) -> None:
    db_session.add_all(
        [
            _departure("past", -1),
            _departure("draft", 2, status="draft"),
            _departure("hidden", 3, is_published=False),
            _departure("closed", 4, status="closed"),
            _departure("later", 20),
            _departure("nearest", 10),
        ]
    )
    await db_session.flush()

    picked = await crud_grouped_departure.get_next_open(db_session, now=NOW)
    assert picked is not None and picked.name == "nearest"

    # Past the nearest cutoff, orders roll over to the following departure.
    later = await crud_grouped_departure.get_next_open(
        db_session, now=NOW + timedelta(days=11)
    )
    assert later is not None and later.name == "later"

    # Nothing open → None: the shop behaves as before departures existed.
    assert (
        await crud_grouped_departure.get_next_open(
            db_session, now=NOW + timedelta(days=30)
        )
        is None
    )


@pytest.mark.asyncio
async def test_admin_lifecycle_and_order_attachment(db_session: AsyncSession) -> None:
    seed = await _seed(db_session)

    created = await create_departure(
        body=GroupedDepartureCreate(
            name="Départ d'octobre", order_cutoff_at=NOW + timedelta(days=14)
        ),
        session=db_session,
        admin=seed.admin,
    )
    assert created.status == "open" and created.orders_count == 0

    # Attach two orders, then move one to a second departure.
    moved = await assign_orders(
        body=AssignOrdersRequest(order_ids=seed.orders[:2], departure_id=created.id),
        session=db_session,
        _admin=seed.admin,
    )
    assert moved.updated == 2

    second = await create_departure(
        body=GroupedDepartureCreate(
            name="Novembre", order_cutoff_at=NOW + timedelta(days=45)
        ),
        session=db_session,
        admin=seed.admin,
    )
    await assign_orders(
        body=AssignOrdersRequest(order_ids=[seed.orders[1]], departure_id=second.id),
        session=db_session,
        _admin=seed.admin,
    )

    listed = {d.name: d for d in await list_departures(db_session, seed.admin)}
    assert listed["Départ d'octobre"].orders_count == 1
    assert listed["Départ d'octobre"].orders_total == Decimal("1000")
    assert listed["Novembre"].orders_count == 1

    # A departure with orders cannot be deleted; detach first, then it can.
    with pytest.raises(AppError) as blocked:
        await delete_departure(second.id, db_session, seed.admin)
    assert blocked.value.code == "grouped_departure.has_orders"
    await assign_orders(
        body=AssignOrdersRequest(order_ids=[seed.orders[1]], departure_id=None),
        session=db_session,
        _admin=seed.admin,
    )
    await delete_departure(second.id, db_session, seed.admin)

    # Partial update: status change + unpublish.
    updated = await update_departure(
        created.id,
        GroupedDepartureUpdate(status="closed", is_published=False),
        db_session,
        seed.admin,
    )
    assert (updated.status, updated.is_published) == ("closed", False)
    with pytest.raises(ValueError):
        GroupedDepartureUpdate(status="lost_at_sea")

    # Assigning to an unknown departure is refused.
    with pytest.raises(AppError) as missing:
        await assign_orders(
            body=AssignOrdersRequest(order_ids=seed.orders, departure_id=uuid.uuid4()),
            session=db_session,
            _admin=seed.admin,
        )
    assert missing.value.code == "grouped_departure.not_found"


@pytest.mark.asyncio
async def test_filtered_orders_export_and_sku_summary(db_session: AsyncSession) -> None:
    seed = await _seed(db_session)
    departure = _departure("Octobre", 14)
    db_session.add(departure)
    await db_session.flush()
    departure_id = departure.id  # assign_orders commits → the row expires
    await crud_grouped_departure.assign_orders(
        db_session, order_ids=seed.orders[:2], departure_id=departure_id
    )

    by_departure = await _list_order_rows(
        db_session, **_filters(departure_id=departure_id), skip=0, limit=None
    )
    assert {r.order_id for r in by_departure} == set(seed.orders[:2])
    assert by_departure[0].order_number == "CMD-2026-00005"  # most recent first

    unassigned = await _list_order_rows(
        db_session, **_filters(unassigned=True), skip=0, limit=None
    )
    assert [r.order_id for r in unassigned] == [seed.orders[2]]

    by_period = await _list_order_rows(
        db_session,
        **_filters(date_from=datetime(2026, 10, 4), date_to=datetime(2026, 10, 10)),
        skip=0,
        limit=None,
    )
    assert {r.order_id for r in by_period} == set(seed.orders[1:])

    by_status = await _list_order_rows(
        db_session, **_filters(status="Pending"), skip=0, limit=None
    )
    assert [r.order_id for r in by_status] == [seed.orders[2]]

    # SKU summary of the departure = the supplier purchase order.
    summary = {
        r.supplier_sku: r
        for r in await _sku_summary_rows(
            db_session, **_filters(departure_id=departure_id)
        )
    }
    assert summary["LT-1"].quantity == 3 and summary["LT-1"].orders_count == 2
    assert summary["LT-1"].unit_cost == 750.0 and summary["LT-1"].cost_currency == "EUR"
    assert summary["LT-1"].total_weight_kg == 7.5
    assert summary["MS-1"].quantity == 3 and summary["MS-1"].unit_cost is None

    csv_orders = await export_orders_csv(
        db_session, seed.admin, **_filters(departure_id=departure_id)
    )
    lines = bytes(csv_orders.body).decode("utf-8-sig").splitlines()
    assert lines[0].startswith("Numéro;Date;Client") and len(lines) == 3
    assert "CMD-2026-00005;2026-10-05;Tehani" in lines[1] and lines[1].endswith(
        "2000,00"
    )

    csv_sku = await sku_summary_csv(
        db_session, seed.admin, **_filters(departure_id=departure_id)
    )
    sku_lines = bytes(csv_sku.body).decode("utf-8-sig").splitlines()
    assert (
        sku_lines[0].startswith("Fournisseur;SKU fournisseur") and len(sku_lines) == 3
    )
    assert "ingram;LT-1;;Laptop;3;2;750,00;EUR;2.5;7.5" in sku_lines


@pytest.mark.asyncio
async def test_public_endpoints_expose_only_published_departures(
    db_session: AsyncSession,
) -> None:
    visible = _departure("Octobre", 14, estimated_delivery_at=NOW + timedelta(days=40))
    hidden = _departure("Interne", 5, is_published=False)
    db_session.add_all([visible, hidden])
    await db_session.flush()

    summary = await get_departure(visible.id, db_session)
    assert summary.name == "Octobre" and summary.estimated_delivery_at is not None
    assert not hasattr(summary, "created_by_id")

    with pytest.raises(AppError):
        await get_departure(hidden.id, db_session)

    # /next is the same resolver as the checkout attachment.
    nxt = await next_departure(db_session)
    assert nxt is not None and nxt.id == visible.id
