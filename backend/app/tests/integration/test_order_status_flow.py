"""Integration tests (real DB): order status service, the admin endpoint and
the propagation of a grouped departure's step to its orders."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from typing import cast

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_grouped_departures import update_departure
from app.api.routes.admin_orders import (
    OrderStatusChangeRequest,
    change_order_status,
    get_order_detail,
)
from app.core.errors import AppError
from app.features.departure.models import GroupedDeparture, GroupedDepartureUpdate
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.status import (
    EVENT_ORDER_STATUS_CHANGED,
    set_order_status,
)
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.user.models.user import User
from app.outbox.models import OutboxEvent

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


async def _seed(session: AsyncSession) -> SimpleNamespace:
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
    paid, pending, refunded = (
        OrderStatus(name="Paid"),
        OrderStatus(name="Pending"),
        OrderStatus(name="Refunded"),
    )
    departure = GroupedDeparture(
        name="Octobre",
        order_cutoff_at=NOW + timedelta(days=10),
        status="closed",
        is_published=True,
    )
    session.add_all([admin, buyer, paid, pending, refunded, departure])
    await session.flush()

    def order(status: OrderStatus, attached: bool = True) -> Order:
        return Order(
            user_id=buyer.id,
            order_status_id=status.id,
            order_number=f"CMD-2026-{uuid.uuid4().int % 100000:05d}",
            total_amount=Decimal("100"),
            grouped_departure_id=departure.id if attached else None,
        )

    orders = [
        order(paid),
        order(paid),
        order(pending),
        order(refunded),
        order(paid, False),
    ]
    session.add_all(orders)
    await session.flush()
    return SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        departure_id=departure.id,
        paid_attached=[orders[0].id, orders[1].id],
        pending_id=orders[2].id,
        refunded_id=orders[3].id,
        paid_detached=orders[4].id,
    )


async def _status_names(session: AsyncSession, order_ids: list[uuid.UUID]) -> set[str]:
    rows = (
        await session.exec(
            select(OrderStatus.name)
            .join(Order, col(Order.order_status_id) == col(OrderStatus.id))
            .where(col(Order.id).in_(order_ids))
        )
    ).all()
    return set(rows)


async def _events(session: AsyncSession) -> list[OutboxEvent]:
    return list(
        (
            await session.exec(
                select(OutboxEvent).where(
                    col(OutboxEvent.type) == EVENT_ORDER_STATUS_CHANGED
                )
            )
        ).all()
    )


@pytest.mark.asyncio
async def test_set_status_creates_the_status_and_publishes_once(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    order = await db_session.get(Order, seed.paid_attached[0])
    assert order is not None

    assert await set_order_status(
        db_session, order=order, status_name="InTransit", changed_by_id=seed.admin.id
    )
    # Same status again: no change, no second event.
    assert not await set_order_status(
        db_session, order=order, status_name="InTransit", changed_by_id=seed.admin.id
    )
    await db_session.commit()

    assert await _status_names(db_session, [seed.paid_attached[0]]) == {"InTransit"}
    events = await _events(db_session)
    assert len(events) == 1
    assert events[0].payload["old_status"] == "Paid"
    assert events[0].payload["new_status"] == "InTransit"
    assert events[0].payload["grouped_departure_id"] == str(seed.departure_id)

    with pytest.raises(ValueError):
        await set_order_status(
            db_session, order=order, status_name="Teleported", changed_by_id=None
        )


@pytest.mark.asyncio
async def test_admin_endpoint_changes_one_order_and_refuses_unknown_status(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    with pytest.raises(AppError) as unknown:
        await change_order_status(
            seed.paid_attached[0],
            OrderStatusChangeRequest(status="Lost"),
            db_session,
            seed.admin,
        )
    assert unknown.value.code == "order.status.unknown"

    result = await change_order_status(
        seed.paid_attached[0],
        OrderStatusChangeRequest(status="ReadyForPickup", reason="retrait"),
        db_session,
        seed.admin,
    )
    assert result.changed and result.status == "ReadyForPickup"
    assert await _status_names(db_session, [seed.paid_attached[0]]) == {
        "ReadyForPickup"
    }
    assert (await _events(db_session))[0].payload["reason"] == "retrait"


@pytest.mark.asyncio
async def test_departure_step_moves_only_the_orders_that_follow_it(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    result = await update_departure(
        seed.departure_id,
        GroupedDepartureUpdate(status="in_transit"),
        db_session,
        seed.admin,
    )
    assert result.status == "in_transit"
    assert result.orders_updated == 2

    assert await _status_names(db_session, seed.paid_attached) == {"InTransit"}
    # Unpaid, refunded and detached orders are left alone.
    assert await _status_names(db_session, [seed.pending_id]) == {"Pending"}
    assert await _status_names(db_session, [seed.refunded_id]) == {"Refunded"}
    assert await _status_names(db_session, [seed.paid_detached]) == {"Paid"}
    assert len(await _events(db_session)) == 2

    # A step with no order mapping (draft / open / closed) moves nothing; a
    # rename does not touch the orders either.
    renamed = await update_departure(
        seed.departure_id,
        GroupedDepartureUpdate(name="Octobre bis"),
        db_session,
        seed.admin,
    )
    assert renamed.orders_updated == 0
    closed = await update_departure(
        seed.departure_id,
        GroupedDepartureUpdate(status="closed"),
        db_session,
        seed.admin,
    )
    assert closed.orders_updated == 0
    assert await _status_names(db_session, seed.paid_attached) == {"InTransit"}


@pytest.mark.asyncio
async def test_admin_detail_reports_the_order_status_not_the_payment_one(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)
    order = await db_session.get(Order, seed.paid_attached[0])
    assert order is not None
    # captured: the commit expires them
    order_id, user_id, order_number = order.id, order.user_id, order.order_number
    completed = PaymentStatus(name="Completed")
    db_session.add(completed)
    await db_session.flush()
    db_session.add(
        Payment(
            amount=Decimal("100"),
            currency="XPF",
            provider_code="manual_transfer",
            order_id=order_id,
            user_id=user_id,
            payment_status_id=completed.id,
        )
    )
    await db_session.commit()

    detail = await get_order_detail(order_id, db_session, seed.admin)
    assert detail.status == "Paid"  # used to come back as "Completed"
    assert detail.order_number == order_number
    assert detail.payments[0].status == "Completed"
