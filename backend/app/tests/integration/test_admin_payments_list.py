"""A19 — the general payments list of the back-office (real DB)."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_payments import list_payments as _list_payments
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.user.models.user import User

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=timezone.utc)


async def list_payments(session: AsyncSession, admin: Any, **filters: Any) -> Any:
    """Call the route with every query parameter spelled out (no Query defaults)."""
    params: dict[str, Any] = {
        "q": None,
        "status": None,
        "provider_code": None,
        "date_from": None,
        "date_to": None,
        "skip": 0,
        "limit": 50,
    }
    params.update(filters)
    return await _list_payments(session, admin, **params)


async def _user(session: AsyncSession, name: str, email: str) -> User:
    user = User(email=email, full_name=name, is_active=True, hashed_password="x")
    session.add(user)
    await session.flush()
    return user


@pytest.mark.asyncio
async def test_payments_list_filters_and_pages(db_session: AsyncSession) -> None:
    admin = await _user(db_session, "Admin", f"a+{uuid.uuid4().hex[:6]}@test.local")
    hina = await _user(
        db_session, "Hina Teriitahi", f"h+{uuid.uuid4().hex[:6]}@test.local"
    )
    moana = await _user(
        db_session, "Moana Tane", f"m+{uuid.uuid4().hex[:6]}@test.local"
    )
    completed = PaymentStatus(name="Completed")
    pending = PaymentStatus(name="Pending")
    order_status = OrderStatus(name="Paid")
    db_session.add_all([completed, pending, order_status])
    await db_session.flush()
    order = Order(
        user_id=hina.id,
        order_status_id=order_status.id,
        total_amount=Decimal("1000"),
        order_number="CMD-2026-00042",
    )
    db_session.add(order)
    await db_session.flush()
    db_session.add_all(
        [
            Payment(
                user_id=hina.id,
                order_id=order.id,
                amount=Decimal("1000"),
                currency="XPF",
                provider_code="manual_transfer",
                provider_reference="VIR-123",
                payment_status_id=completed.id,
                created_at=NOW,
            ),
            Payment(
                user_id=moana.id,
                amount=Decimal("500"),
                currency="XPF",
                provider_code="payzen",
                payment_status_id=pending.id,
                created_at=NOW - timedelta(days=3),
            ),
            Payment(
                user_id=moana.id,
                amount=Decimal("250"),
                currency="XPF",
                provider_code="payzen",
                payment_status_id=completed.id,
                created_at=NOW - timedelta(days=40),
            ),
        ]
    )
    await db_session.commit()
    admin_view = cast(Any, admin)

    everything = await list_payments(db_session, admin_view)
    assert everything.count == 3
    assert [p.amount for p in everything.data] == [1000.0, 500.0, 250.0]  # newest first
    first = everything.data[0]
    assert first.status == "Completed" and first.order_number == "CMD-2026-00042"
    assert first.user_name == "Hina Teriitahi" and first.provider_reference == "VIR-123"
    assert set(everything.statuses) >= {"Completed", "Pending"}
    assert everything.provider_codes == ["manual_transfer", "payzen"]

    by_status = await list_payments(db_session, admin_view, status="Pending")
    assert [p.amount for p in by_status.data] == [500.0] and by_status.count == 1

    by_provider = await list_payments(db_session, admin_view, provider_code="payzen")
    assert by_provider.count == 2

    by_order = await list_payments(db_session, admin_view, q="cmd-2026-00042")
    assert [p.amount for p in by_order.data] == [1000.0]
    by_name = await list_payments(db_session, admin_view, q="moana")
    assert by_name.count == 2
    by_reference = await list_payments(db_session, admin_view, q="VIR-1")
    assert by_reference.count == 1

    recent = await list_payments(
        db_session, admin_view, date_from=date(2026, 9, 28), date_to=date(2026, 10, 2)
    )
    assert [p.amount for p in recent.data] == [1000.0, 500.0]

    page_two = await list_payments(db_session, admin_view, skip=1, limit=1)
    assert page_two.count == 3 and [p.amount for p in page_two.data] == [500.0]
