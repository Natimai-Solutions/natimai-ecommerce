"""Integration (real DB): what the review of the audit fixes found around the
stock and the order status (audit 2026-11, B1/B2/B6 follow-up).

A refusal only undoes an order still waiting for its money; money that
arrives after the reservation was given back takes it again, or alerts."""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Any

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.features.inventory.models.inventory import Inventory
from app.features.inventory.models.stock_movement import (
    InventoryStockMovement,
    MovementStatus,
    MovementType,
    ReferenceType,
)
from app.features.inventory.services.stock_release import release_order_stock
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.product.models.product import Product
from app.handlers import payment as handlers
from app.tests.integration.test_customer_cancel_and_reorder import (
    _order,
    _status,
    _status_name_of,
    _user,
)


async def _reserve_one(
    session: AsyncSession, order_id: uuid.UUID
) -> tuple[uuid.UUID, uuid.UUID]:
    """One warehouse unit reserved for the order (stock left: 0)."""
    product = Product(name="Casque", base_price=Decimal("30000"))
    session.add(product)
    await session.flush()
    inventory = Inventory(
        product_id=product.id, quantity=Decimal("0"), compute_from_movements=False
    )
    session.add(inventory)
    session.add(
        InventoryStockMovement(
            movement_type=MovementType.OUTGOING.value,
            reference_type=ReferenceType.ORDER.value,
            reference_id=order_id,
            product_id=product.id,
            quantity=Decimal("1"),
            reason="Local stock reserved during checkout (segment=local)",
            status=MovementStatus.PENDING.value,
        )
    )
    await session.flush()
    ids = (product.id, inventory.id)
    await session.commit()
    return ids


async def _quantity(session: AsyncSession, inventory_id: uuid.UUID) -> Decimal:
    session.expire_all()
    inventory = await session.get(Inventory, inventory_id)
    assert inventory is not None
    return inventory.quantity


def _payload(order_id: uuid.UUID, payment_id: uuid.UUID) -> dict[str, Any]:
    return {"order_id": str(order_id), "payment_id": str(payment_id)}


@pytest.mark.asyncio
async def test_a_refusal_does_not_revive_a_cancelled_order(
    db_session: AsyncSession,
) -> None:
    """The admin cancels, then rejects the transfer still waiting: the order
    came back « PaymentFailed », payable, its coupon already given back."""
    buyer = await _user(db_session)
    order_id, payment_id = await _order(
        db_session, buyer, order_status="Cancelled", payment_status="Failed"
    )

    await handlers.on_payment_rejected(db_session, _payload(order_id, payment_id))

    order = await db_session.get(Order, order_id)
    assert order is not None
    assert await _status_name_of(db_session, order) == "Cancelled"


@pytest.mark.asyncio
async def test_a_late_refusal_leaves_an_order_paid_by_another_attempt(
    db_session: AsyncSession,
) -> None:
    buyer = await _user(db_session)
    buyer_id = buyer.id
    order_id, first_id = await _order(
        db_session, buyer, order_status="Pending", payment_status="Failed"
    )
    _, inventory_id = await _reserve_one(db_session, order_id)
    db_session.add(
        Payment(
            order_id=order_id,
            user_id=buyer_id,
            amount=Decimal("30000"),
            currency="XPF",
            provider_code="payzen",
            payment_status_id=await _status(db_session, PaymentStatus, "Authorized"),
        )
    )
    await db_session.commit()

    await handlers.on_payment_rejected(db_session, _payload(order_id, first_id))

    order = await db_session.get(Order, order_id)
    assert order is not None
    assert await _status_name_of(db_session, order) == "Pending"
    assert await _quantity(db_session, inventory_id) == Decimal("0")  # still held


@pytest.mark.asyncio
async def test_money_after_a_release_takes_the_stock_again_or_alerts(
    db_session: AsyncSession, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A capture confirmed nothing when the reservation had been given back
    (sweep, counter receipt, late notification): sold without stock, silently."""
    alerts: list[str] = []

    async def _alert(message: str, **_kwargs: object) -> bool:
        alerts.append(message)
        return True

    monkeypatch.setattr(handlers, "send_alert", _alert)
    buyer = await _user(db_session)

    # 1. The unit is still there: taken again, then confirmed.
    order_id, payment_id = await _order(
        db_session, buyer, order_status="Pending", payment_status="Completed"
    )
    _, inventory_id = await _reserve_one(db_session, order_id)
    await release_order_stock(db_session, order_id=order_id)
    await db_session.commit()
    assert await _quantity(db_session, inventory_id) == Decimal("1")

    await handlers.on_payment_captured(db_session, _payload(order_id, payment_id))

    assert await _quantity(db_session, inventory_id) == Decimal("0")
    order = await db_session.get(Order, order_id)
    assert order is not None
    assert await _status_name_of(db_session, order) == "Paid"
    assert alerts == []

    # 2. Someone else bought it meanwhile: the admin is told.
    other_id, other_payment = await _order(
        db_session, buyer, order_status="Pending", payment_status="Completed"
    )
    _, other_inventory = await _reserve_one(db_session, other_id)
    await release_order_stock(db_session, order_id=other_id)
    inventory = await db_session.get(Inventory, other_inventory)
    assert inventory is not None
    inventory.quantity = Decimal("0")
    await db_session.commit()

    await handlers.on_payment_captured(db_session, _payload(other_id, other_payment))

    assert len(alerts) == 1 and str(other_id) in alerts[0]


@pytest.mark.asyncio
async def test_a_balance_by_transfer_does_not_send_the_order_back(
    db_session: AsyncSession,
) -> None:
    """« awaiting validation » on the balance of an order in transit moved it
    to « AwaitingPayment », where it stayed once the balance was validated."""
    buyer = await _user(db_session)
    order_id, payment_id = await _order(
        db_session, buyer, order_status="InTransit", payment_status="AwaitingValidation"
    )

    await handlers.on_payment_awaiting_validation(
        db_session, _payload(order_id, payment_id)
    )
    await handlers.on_payment_document_required(
        db_session, _payload(order_id, payment_id)
    )

    order = await db_session.get(Order, order_id)
    assert order is not None
    assert await _status_name_of(db_session, order) == "InTransit"

    # An order still waiting for its first payment does move.
    fresh_id, fresh_payment = await _order(
        db_session, buyer, order_status="Pending", payment_status="AwaitingValidation"
    )
    await handlers.on_payment_awaiting_validation(
        db_session, _payload(fresh_id, fresh_payment)
    )
    fresh = await db_session.get(Order, fresh_id)
    assert fresh is not None
    assert await _status_name_of(db_session, fresh) == "AwaitingPayment"


@pytest.mark.asyncio
async def test_a_validated_manual_payment_cannot_be_rejected(
    db_session: AsyncSession,
) -> None:
    from types import SimpleNamespace
    from typing import cast

    from app.features.payment.services.manual_payment import (
        PaymentNotAwaitingError,
        reject_manual_payment,
    )
    from app.features.user.models.user import User

    buyer = await _user(db_session)
    _, payment_id = await _order(
        db_session, buyer, order_status="Paid", payment_status="Completed"
    )
    payment = await db_session.get(Payment, payment_id)
    assert payment is not None
    payment.provider_code = "manual_transfer"
    await db_session.commit()
    await db_session.refresh(payment)

    with pytest.raises(PaymentNotAwaitingError):
        await reject_manual_payment(
            db_session,
            payment=payment,
            admin=cast(User, SimpleNamespace(id=uuid.uuid4())),
            reason="erreur",
        )


@pytest.mark.asyncio
async def test_cash_for_an_order_without_stock_is_refused(
    db_session: AsyncSession,
) -> None:
    from app.core.errors import AppError
    from app.features.payment.services.receipts import record_counter_payment

    buyer = await _user(db_session)
    order_id, _ = await _order(
        db_session, buyer, order_status="PaymentFailed", payment_status="Failed"
    )
    _, inventory_id = await _reserve_one(db_session, order_id)
    await release_order_stock(db_session, order_id=order_id)
    inventory = await db_session.get(Inventory, inventory_id)
    assert inventory is not None
    inventory.quantity = Decimal("0")  # sold to someone else
    await db_session.commit()
    order = await db_session.get(Order, order_id)
    assert order is not None
    await db_session.refresh(order)
    await db_session.refresh(buyer)

    with pytest.raises(AppError) as refused:
        await record_counter_payment(
            db_session,
            order=order,
            admin=buyer,
            amount=Decimal("30000"),
            method="cash",
        )
    assert refused.value.code == "payment.order.out_of_stock"

    cancelled = await _status(db_session, OrderStatus, "Cancelled")
    order.order_status_id = cancelled
    await db_session.commit()
    await db_session.refresh(order)
    await db_session.refresh(buyer)
    with pytest.raises(AppError) as closed:
        await record_counter_payment(
            db_session,
            order=order,
            admin=buyer,
            amount=Decimal("30000"),
            method="cash",
        )
    assert closed.value.code == "payment.order.cancelled"


@pytest.mark.asyncio
async def test_a_closed_or_paid_order_does_not_go_back(
    db_session: AsyncSession,
) -> None:
    """Functional audit, November 2026: any status followed any other —
    « Cancelled → Paid » revived an order without its stock, « Delivered →
    Pending » made it payable again."""
    from types import SimpleNamespace
    from typing import cast

    from app.api.routes.admin_orders import (
        OrderStatusChangeRequest,
        change_order_status,
    )
    from app.core.errors import AppError

    admin = cast(Any, SimpleNamespace(id=uuid.uuid4()))
    buyer = await _user(db_session)
    cancelled_id, _ = await _order(
        db_session, buyer, order_status="Cancelled", payment_status="Cancelled"
    )
    delivered_id, _ = await _order(
        db_session, buyer, order_status="Delivered", payment_status="Completed"
    )

    for order_id, target in ((cancelled_id, "Paid"), (delivered_id, "Pending")):
        with pytest.raises(AppError) as refused:
            await change_order_status(
                order_id, OrderStatusChangeRequest(status=target), db_session, admin
            )
        assert refused.value.code == "order.status.transition_refused"

    # A fulfilment step back (a wrong click corrected) stays possible.
    moved = await change_order_status(
        delivered_id,
        OrderStatusChangeRequest(status="ReadyForPickup"),
        db_session,
        admin,
    )
    assert moved.changed is True


@pytest.mark.asyncio
async def test_a_refused_status_on_the_generic_put_saves_nothing(
    db_session: AsyncSession,
) -> None:
    """Review of 17/11/2026: the other fields of the PUT were committed, then
    the status change refused — half a write behind a 409."""
    from sqlmodel import col, select

    from app.api.routes.order import router as order_router
    from app.core.errors import AppError
    from app.features.order.models.order import Order, OrderUpdate
    from app.features.order.models.order_status import OrderStatus

    admin = await _user(db_session)
    admin.is_superuser = True
    db_session.add(admin)
    await db_session.commit()
    buyer = await _user(db_session)
    order_id, _ = await _order(
        db_session, buyer, order_status="Cancelled", payment_status="Cancelled"
    )
    paid = (
        await db_session.exec(
            select(OrderStatus).where(col(OrderStatus.name) == "Paid")
        )
    ).first()
    if paid is None:
        paid = OrderStatus(name="Paid")
        db_session.add(paid)
        await db_session.flush()
    paid_id = paid.id
    await db_session.commit()
    await db_session.refresh(admin)

    update = order_router.generate_update_endpoint()
    with pytest.raises(AppError) as refused:
        await update(
            session=db_session,
            id=order_id,
            data=OrderUpdate(notes="ne doit pas rester", order_status_id=paid_id),
            current_user=admin,
        )
    assert refused.value.code == "order.status.transition_refused"

    db_session.expire_all()
    order = await db_session.get(Order, order_id)
    assert order is not None and order.notes != "ne doit pas rester"
