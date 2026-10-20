"""Integration tests (real DB): assisted close, thresholds and recurrence,
supplier orders recorded on the departure, reminders (schedule, render,
publish through the webhook, cancellation on a closed departure)."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_grouped_departures import (
    CloseRequest,
    add_supplier_order,
    close_departure_endpoint,
    create_departure,
    create_reminder,
    list_reminders,
    publish_reminder_now,
    update_departure,
)
from app.core.errors import AppError
from app.features.departure import services
from app.features.departure.models import (
    DepartureReminder,
    DepartureReminderWrite,
    GroupedDeparture,
    GroupedDepartureCreate,
    GroupedDepartureUpdate,
    SupplierOrderEntry,
)
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.product import Product
from app.features.system.models.system_setting import SystemSetting
from app.features.user.models.user import User

NOW = datetime(2026, 10, 1, 12, 0, tzinfo=UTC)


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
    paid, pending = OrderStatus(name="Paid"), OrderStatus(name="Pending")
    laptop = Product(
        name="Laptop",
        supplier_name="ingram_micro",
        supplier_sku="LT-1",
        is_supplier_managed=True,
        supplier_quantity=Decimal("10"),
    )
    mouse = Product(name="Souris", supplier_name="local", supplier_sku="MS-1")
    departure = GroupedDeparture(
        name="Octobre",
        order_cutoff_at=NOW + timedelta(days=10),
        estimated_delivery_at=NOW + timedelta(days=40),
        status="open",
        is_published=True,
        recurrence_days=30,
    )
    session.add_all([admin, buyer, paid, pending, laptop, mouse, departure])
    await session.flush()

    def order(status: OrderStatus, total: str) -> Order:
        return Order(
            user_id=buyer.id,
            order_status_id=status.id,
            order_number=f"CMD-{uuid.uuid4().hex[:6]}",
            total_amount=Decimal(total),
            grouped_departure_id=departure.id,
        )

    o1, o2, o3 = order(paid, "1000"), order(paid, "2000"), order(pending, "50")
    session.add_all([o1, o2, o3])
    await session.flush()
    session.add_all(
        [
            OrderLine(
                order_id=o1.id,
                product_id=laptop.id,
                quantity=2,
                unit_price=Decimal(500),
            ),
            OrderLine(
                order_id=o2.id,
                product_id=laptop.id,
                quantity=3,
                unit_price=Decimal(500),
            ),
            OrderLine(
                order_id=o2.id, product_id=mouse.id, quantity=1, unit_price=Decimal(10)
            ),
        ]
    )
    await session.flush()
    return SimpleNamespace(
        admin=cast(User, SimpleNamespace(id=admin.id)),
        departure_id=departure.id,
        laptop_id=laptop.id,
        paid_ids=[o1.id, o2.id],
        pending_id=o3.id,
    )


def _fake_availability(quantities: dict[str, str]) -> AsyncMock:
    async def refresh(_session: Any, products: list[Product]) -> dict[str, Decimal]:
        out: dict[str, Decimal] = {}
        for p in products:
            if p.supplier_sku in quantities:
                out[str(p.supplier_sku)] = Decimal(quantities[str(p.supplier_sku)])
        return out

    return AsyncMock(side_effect=refresh)


@pytest.mark.asyncio
async def test_close_reports_shortages_and_unpaid_and_spawns_the_next_departure(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(db_session)
    # The supplier now shows 4 laptops for 5 ordered; the mouse has no live stock.
    monkeypatch.setattr(
        services, "refresh_supplier_availability", _fake_availability({"LT-1": "4"})
    )

    result = await close_departure_endpoint(
        seed.departure_id, CloseRequest(), db_session, seed.admin
    )
    assert result.closed and result.threshold_reached
    assert result.orders_count == 2 and result.orders_total == Decimal("3000")
    assert result.unpaid_order_ids == [seed.pending_id]
    assert len(result.shortages) == 1
    shortage = result.shortages[0]
    assert shortage.supplier_sku == "LT-1"
    assert (shortage.ordered_quantity, shortage.available_quantity) == (5, 4)
    assert set(shortage.order_ids) == set(seed.paid_ids)

    closed = await db_session.get(GroupedDeparture, seed.departure_id)
    assert closed is not None and closed.status == "closed" and not closed.is_published

    # Recurring: the next departure is open, published, 30 days later.
    assert result.next_departure_id is not None
    nxt = await db_session.get(GroupedDeparture, result.next_departure_id)
    assert nxt is not None and nxt.status == "open" and nxt.is_published
    assert nxt.order_cutoff_at - closed.order_cutoff_at == timedelta(days=30)
    assert nxt.recurrence_days == 30

    # Closing twice is refused.
    with pytest.raises(AppError) as again:
        await close_departure_endpoint(
            seed.departure_id, CloseRequest(), db_session, seed.admin
        )
    assert again.value.code == "grouped_departure.not_open"


@pytest.mark.asyncio
async def test_threshold_not_reached_keeps_the_departure_open_unless_forced(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(db_session)
    monkeypatch.setattr(
        services, "refresh_supplier_availability", _fake_availability({})
    )
    departure = await db_session.get(GroupedDeparture, seed.departure_id)
    assert departure is not None
    departure.min_amount = Decimal("5000")
    departure.recurrence_days = None
    db_session.add(departure)
    await db_session.commit()

    result = await close_departure_endpoint(
        seed.departure_id, CloseRequest(), db_session, seed.admin
    )
    assert not result.closed and not result.threshold_reached
    still = await db_session.get(GroupedDeparture, seed.departure_id)
    assert still is not None and still.status == "open"

    forced = await close_departure_endpoint(
        seed.departure_id, CloseRequest(force=True), db_session, seed.admin
    )
    assert forced.closed and forced.next_departure_id is None


@pytest.mark.asyncio
async def test_supplier_order_is_recorded_and_moves_the_departure_to_ordered(
    db_session: AsyncSession,
) -> None:
    seed = await _seed(db_session)

    result = await add_supplier_order(
        seed.departure_id,
        SupplierOrderEntry(
            supplier_name="ingram_micro",
            order_number="IM-123456",
            ordered_at=NOW,
            total_amount=Decimal("2400.50"),
            currency="EUR",
        ),
        db_session,
        seed.admin,
    )
    assert result.status == "ordered"
    assert result.orders_updated == 2  # the two paid orders, not the pending one
    assert (
        result.supplier_orders
        and result.supplier_orders[0]["order_number"] == "IM-123456"
    )

    names = (
        await db_session.exec(
            select(OrderStatus.name)
            .join(Order, col(Order.order_status_id) == col(OrderStatus.id))
            .where(col(Order.id).in_(seed.paid_ids))
        )
    ).all()
    assert set(names) == {"OrderedFromSupplier"}


@pytest.mark.asyncio
async def test_reminders_are_scheduled_rendered_and_published(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The default reminders are only created while still in the future, against
    # the real clock: pin it to the fixtures' NOW so the J-7 and J-2 ones do not
    # vanish once the hard-coded October cutoff is less than a week away.
    monkeypatch.setattr(services, "utcnow", lambda: NOW)
    seed = await _seed(db_session)
    created = await create_departure(
        GroupedDepartureCreate(
            name="Novembre",
            order_cutoff_at=NOW + timedelta(days=20),
            estimated_delivery_at=NOW + timedelta(days=50),
        ),
        db_session,
        seed.admin,
    )
    reminders = await list_reminders(created.id, db_session, seed.admin)
    assert [r.offset_days for r in reminders] == [7, 2, 0]
    assert all(r.status == "scheduled" for r in reminders)
    assert "Novembre" in reminders[0].rendered_text
    assert (
        reminders[0].scheduled_at
        < reminders[1].scheduled_at
        < reminders[2].scheduled_at
    )

    # Moving the cutoff reschedules the pending reminders.
    before = reminders[0].scheduled_at
    await update_departure(
        created.id,
        GroupedDepartureUpdate(order_cutoff_at=NOW + timedelta(days=25)),
        db_session,
        seed.admin,
    )
    after = (await list_reminders(created.id, db_session, seed.admin))[0].scheduled_at
    assert after - before == timedelta(days=5)

    # A custom reminder with the template variables.
    custom = await create_reminder(
        created.id,
        DepartureReminderWrite(
            offset_days=1,
            message_template="J-{days_left} : « {name} » clôture le {cutoff_date}",
        ),
        db_session,
        seed.admin,
    )
    assert custom.rendered_text.startswith("J-") and "Novembre" in custom.rendered_text

    # Publish now: no webhook configured → failed with a clear reason.
    failed = await publish_reminder_now(custom.id, db_session, seed.admin)
    assert failed.status == "failed" and "webhook" in (failed.error or "").lower()

    # With a webhook: posted, recorded as sent.
    db_session.add(SystemSetting(key="social_webhook_url", value="https://hook.test/x"))
    await db_session.commit()
    posted: list[dict[str, Any]] = []

    async def fake_post(url: str, payload: dict[str, Any]) -> tuple[bool, str | None]:
        posted.append({"url": url, **payload})
        return True, None

    monkeypatch.setattr(services, "post_json", fake_post)
    sent = await publish_reminder_now(custom.id, db_session, seed.admin)
    assert sent.status == "sent" and sent.sent_at is not None
    assert posted[0]["url"] == "https://hook.test/x"
    assert posted[0]["text"] == sent.rendered_text
    assert posted[0]["departure"]["name"] == "Novembre"


@pytest.mark.asyncio
async def test_due_reminders_post_and_closed_departures_are_cancelled(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    seed = await _seed(db_session)
    departure = await db_session.get(GroupedDeparture, seed.departure_id)
    assert departure is not None
    due = await services.add_reminder(
        db_session,
        departure,
        DepartureReminderWrite(offset_days=0, message_template="Dernier jour {name}"),
    )
    due.scheduled_at = NOW - timedelta(hours=1)
    later = await services.add_reminder(
        db_session,
        departure,
        DepartureReminderWrite(offset_days=2, message_template="Bientôt {name}"),
    )
    later.scheduled_at = NOW + timedelta(days=3)
    db_session.add_all([due, later])
    db_session.add(SystemSetting(key="social_webhook_url", value="https://hook.test/x"))
    await db_session.commit()
    monkeypatch.setattr(services, "post_json", AsyncMock(return_value=(True, None)))

    assert await services.publish_due_reminders(db_session, now=NOW) == {
        "sent": 1,
        "failed": 0,
        "cancelled": 0,
    }
    statuses = {
        r.offset_days: r.status
        for r in (
            await db_session.exec(
                select(DepartureReminder).where(
                    col(DepartureReminder.grouped_departure_id) == seed.departure_id
                )
            )
        ).all()
    }
    assert statuses == {0: "sent", 2: "scheduled"}

    # Once the departure is closed, its remaining reminders are cancelled
    # instead of advertising a departure nobody can join.
    departure = await db_session.get(GroupedDeparture, seed.departure_id)
    assert departure is not None
    departure.status = "closed"
    db_session.add(departure)
    await db_session.commit()
    assert await services.publish_due_reminders(
        db_session, now=NOW + timedelta(days=4)
    ) == {"sent": 0, "failed": 0, "cancelled": 1}
