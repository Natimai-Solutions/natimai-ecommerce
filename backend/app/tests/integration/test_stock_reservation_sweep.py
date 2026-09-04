"""Integration tests: reservations of orders that never got paid are released.

Real DB. Before the sweep existed, ``release_order_stock`` was only ever
reached by ``payment.rejected`` — a customer who opened the payment page and
closed the tab held the stock indefinitely.
"""

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.features.inventory.crud import crud_stock_movement
from app.features.inventory.models.inventory import Inventory
from app.features.inventory.models.stock_movement import (
    InventoryStockMovement,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.product.models.product import Product
from app.features.user.models.user import User
from app.tasks import inventory_tasks


async def _status(session: AsyncSession, name: str) -> OrderStatus:
    status = OrderStatus(name=name)
    session.add(status)
    await session.flush()
    return status


async def _seed_order_with_reservation(
    session: AsyncSession,
    *,
    status_name: str,
    reserved_hours_ago: int,
) -> tuple[uuid.UUID, uuid.UUID, uuid.UUID]:
    """One order holding 2 local + 3 supplier units, aged as requested."""
    status = await _status(session, status_name)

    customer = User(
        email=f"c+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    session.add(customer)
    await session.flush()

    product = Product(
        name=f"Produit {uuid.uuid4().hex[:6]}",
        base_price=Decimal("1000.00"),
        supplier_quantity=Decimal("7.00"),
        is_supplier_managed=True,
    )
    session.add(product)
    await session.flush()

    inventory = Inventory(
        product_id=product.id,
        place_id=None,
        quantity=Decimal("1.00"),
        compute_from_movements=False,
    )
    session.add(inventory)

    order = Order(
        user_id=customer.id,
        order_status_id=status.id,
        total_amount=Decimal("1000.00"),
    )
    session.add(order)
    await session.flush()

    reserved_at = datetime.now(timezone.utc) - timedelta(hours=reserved_hours_ago)
    for quantity, reason in (
        (Decimal("2.00"), "Local stock reserved during checkout (segment=local)"),
        (Decimal("3.00"), "Supplier stock reserved (segment=supplier_direct)"),
    ):
        session.add(
            InventoryStockMovement(
                movement_type=MovementType.OUTGOING.value,
                reference_type=ReferenceType.ORDER.value,
                reference_id=order.id,
                product_id=product.id,
                from_place_id=None,
                quantity=quantity,
                reason=reason,
                status=MovementStatus.PENDING.value,
                created_at=reserved_at,
            )
        )
    await session.flush()
    return order.id, product.id, inventory.id


@pytest.mark.asyncio
async def test_stale_query_ignores_fresh_reservations(
    db_session: AsyncSession,
) -> None:
    """An order being checked out right now must never be swept."""
    fresh_id, _, _ = await _seed_order_with_reservation(
        db_session, status_name="Pending", reserved_hours_ago=0
    )
    stale_id, _, _ = await _seed_order_with_reservation(
        db_session, status_name="Pending", reserved_hours_ago=72
    )
    await db_session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    stale = await crud_stock_movement.get_stale_order_reference_ids(
        db_session, older_than=cutoff
    )

    assert stale_id in stale
    assert fresh_id not in stale


@pytest.mark.asyncio
async def test_stale_query_ignores_already_settled_movements(
    db_session: AsyncSession,
) -> None:
    """COMPLETED and CANCELLED movements hold no stock any more."""
    order_id, _, _ = await _seed_order_with_reservation(
        db_session, status_name="Pending", reserved_hours_ago=72
    )
    movements = await crud_stock_movement.get_by_reference(
        db_session, reference_type=ReferenceType.ORDER.value, reference_id=order_id
    )
    for movement in movements:
        movement.status = MovementStatus.COMPLETED.value
        db_session.add(movement)
    await db_session.commit()

    cutoff = datetime.now(timezone.utc) - timedelta(hours=48)
    stale = await crud_stock_movement.get_stale_order_reference_ids(
        db_session, older_than=cutoff
    )

    assert order_id not in stale


@pytest.mark.asyncio
async def test_sweep_releases_an_abandoned_pending_order(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order_id, product_id, inventory_id = await _seed_order_with_reservation(
        db_session, status_name="Pending", reserved_hours_ago=72
    )
    await db_session.commit()

    result = await _run_sweep(db_session, monkeypatch)

    assert result["status"] == "ok"
    assert result["released_orders"] == 1
    assert result["released_movements"] == 2

    db_session.expire_all()
    product = await db_session.get(Product, product_id)
    inventory = await db_session.get(Inventory, inventory_id)
    assert product is not None and inventory is not None
    assert product.supplier_quantity == Decimal("10.00")  # 7 + 3
    assert inventory.quantity == Decimal("3.00")  # 1 + 2

    movements = await crud_stock_movement.get_by_reference(
        db_session, reference_type=ReferenceType.ORDER.value, reference_id=order_id
    )
    assert {m.status for m in movements} == {MovementStatus.CANCELLED.value}


@pytest.mark.asyncio
async def test_sweep_leaves_awaiting_payment_alone(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A bank transfer under validation is slow on purpose, not abandoned."""
    _, product_id, inventory_id = await _seed_order_with_reservation(
        db_session, status_name="AwaitingPayment", reserved_hours_ago=200
    )
    await db_session.commit()

    result = await _run_sweep(db_session, monkeypatch)

    assert result["released_orders"] == 0
    assert result["skipped_orders"] == 1

    db_session.expire_all()
    product = await db_session.get(Product, product_id)
    inventory = await db_session.get(Inventory, inventory_id)
    assert product is not None and inventory is not None
    assert product.supplier_quantity == Decimal("7.00")
    assert inventory.quantity == Decimal("1.00")


@pytest.mark.asyncio
async def test_sweep_leaves_paid_orders_alone(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, product_id, _ = await _seed_order_with_reservation(
        db_session, status_name="Paid", reserved_hours_ago=200
    )
    await db_session.commit()

    result = await _run_sweep(db_session, monkeypatch)

    assert result["released_orders"] == 0
    assert result["skipped_orders"] == 1
    db_session.expire_all()
    product = await db_session.get(Product, product_id)
    assert product is not None
    assert product.supplier_quantity == Decimal("7.00")


@pytest.mark.asyncio
async def test_sweep_is_idempotent(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second run must not credit the same quantities twice."""
    _, product_id, _ = await _seed_order_with_reservation(
        db_session, status_name="Pending", reserved_hours_ago=72
    )
    await db_session.commit()

    first = await _run_sweep(db_session, monkeypatch)
    second = await _run_sweep(db_session, monkeypatch)

    assert first["released_movements"] == 2
    assert second["released_movements"] == 0

    db_session.expire_all()
    product = await db_session.get(Product, product_id)
    assert product is not None
    assert product.supplier_quantity == Decimal("10.00")


@pytest.mark.asyncio
async def test_sweep_disabled_by_a_zero_ttl(
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, product_id, _ = await _seed_order_with_reservation(
        db_session, status_name="Pending", reserved_hours_ago=200
    )
    await db_session.commit()

    monkeypatch.setattr(settings, "STOCK_RESERVATION_TTL_HOURS", 0, raising=False)
    result = await inventory_tasks.release_expired_stock_reservations_task({})

    assert result["status"] == "disabled"
    db_session.expire_all()
    product = await db_session.get(Product, product_id)
    assert product is not None
    assert product.supplier_quantity == Decimal("7.00")


def test_cron_job_is_registered_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(settings, "STOCK_RESERVATION_TTL_HOURS", 48, raising=False)
    jobs = inventory_tasks.get_stock_reservation_cron_jobs()
    assert len(jobs) == 1


def test_cron_job_absent_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(settings, "STOCK_RESERVATION_TTL_HOURS", 0, raising=False)
    assert inventory_tasks.get_stock_reservation_cron_jobs() == []


async def _run_sweep(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Any]:
    """Run the task against the test session instead of a fresh engine one."""

    class _SessionCtx:
        async def __aenter__(self) -> AsyncSession:
            return db_session

        async def __aexit__(self, *_exc: object) -> None:
            return None

    monkeypatch.setattr(settings, "STOCK_RESERVATION_TTL_HOURS", 48, raising=False)
    monkeypatch.setattr(inventory_tasks, "AsyncSession", lambda _engine: _SessionCtx())
    return await inventory_tasks.release_expired_stock_reservations_task({})
