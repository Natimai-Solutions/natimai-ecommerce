"""Integration tests (real DB): following an order from the signed link in
its e-mails — no account, one order, read-only; anything else reads as an
unknown order."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.orders_me import track_order_by_link
from app.core.errors import AppError
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.tracking_link import (
    order_tracking_token,
    order_tracking_url,
    tracking_url_from_payload,
    verify_order_tracking_token,
)
from app.features.product.models.product import Product
from app.features.user.models.user import User


def test_token_is_bound_to_the_order() -> None:
    order_id, other_id = uuid.uuid4(), uuid.uuid4()
    token = order_tracking_token(order_id)
    assert len(token) == 32 and "=" not in token
    assert verify_order_tracking_token(order_id, token)
    assert verify_order_tracking_token(order_id, f" {token} ")
    assert not verify_order_tracking_token(other_id, token)
    # Tamper with the last character (never replaced by itself: 1 in 64 flake).
    tampered = token[:-1] + ("x" if token[-1] != "x" else "y")
    assert not verify_order_tracking_token(order_id, tampered)
    assert not verify_order_tracking_token(order_id, None)
    assert not verify_order_tracking_token(order_id, "")
    assert order_tracking_url(order_id).endswith(f"/suivi/{order_id}?t={token}")
    assert tracking_url_from_payload(str(order_id)) == order_tracking_url(order_id)
    assert tracking_url_from_payload("not-an-id") is None
    assert tracking_url_from_payload(None) is None


@pytest.mark.asyncio
async def test_the_link_opens_that_order_only(db_session: AsyncSession) -> None:
    buyer = User(
        email=f"buyer+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        hashed_password="x",
    )
    status = OrderStatus(name="InTransit")
    product = Product(name="Écran", supplier_quantity=Decimal("2"), warranty_months=24)
    db_session.add_all([buyer, status, product])
    await db_session.flush()
    order = Order(
        user_id=buyer.id,
        order_status_id=status.id,
        order_number=f"CMD-{uuid.uuid4().hex[:6]}",
        currency="XPF",
        subtotal_amount=Decimal("50000"),
        total_amount=Decimal("50000"),
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add(
        OrderLine(
            order_id=order.id,
            product_id=product.id,
            quantity=1,
            unit_price=Decimal("50000"),
        )
    )
    order_id = order.id
    await db_session.commit()

    # The signed link: order, status, tracking and lines, nothing to sign in to.
    view = await track_order_by_link(
        order_id, db_session, order_tracking_token(order_id)
    )
    assert view.order.id == order_id and view.order.order_status_name == "InTransit"
    assert (
        view.tracking.order_id == order_id and view.tracking.overall_status == "unknown"
    )
    assert [(line.product_name, line.warranty_months) for line in view.lines] == [
        ("Écran", 24)
    ]

    # A missing, forged or foreign token reads like an unknown order.
    for token in (None, "", "forged", order_tracking_token(uuid.uuid4())):
        with pytest.raises(AppError) as refused:
            await track_order_by_link(order_id, db_session, token)
        assert refused.value.status_code == 404
    # …and a genuine token for an order that does not exist too.
    ghost = uuid.uuid4()
    with pytest.raises(AppError) as missing:
        await track_order_by_link(ghost, db_session, order_tracking_token(ghost))
    assert missing.value.code == "order.not_found"
