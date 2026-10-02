"""Integration tests (real DB): the admin home page counters. Each « À
traiter » counter must match the rows of the screen it links to; activity
counts sales by creation date in the shop's time zone; the next departure is
the open one, else the next draft."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, cast

import pytest
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.routes.admin_dashboard import build_dashboard, get_admin_dashboard
from app.api.routes.admin_payments import list_pending_validation
from app.api.routes.admin_quote_requests import list_quote_requests
from app.core.config import settings
from app.features.cart.models.cart import Cart
from app.features.cart.models.quote_request import QuoteRequest
from app.features.departure.models import GroupedDeparture
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.payment.models.payment import Payment
from app.features.payment.models.payment_status import PaymentStatus
from app.features.product.models.currency_rate import (
    CurrencyRate,
    CurrencyRateSource,
)
from app.features.product.models.price_group import PriceGroup
from app.features.product.models.product import (
    AvailabilityMode,
    PricingMode,
    Product,
)
from app.features.user.models.group_upgrade_request import (
    GroupUpgradeRequest,
    UpgradeRequestStatus,
)
from app.features.user.models.user import User

# 02:00 in Tahiti (UTC-10): local midnight is 2026-10-01 10:00 UTC.
NOW = datetime(2026, 10, 1, 12, 0, tzinfo=timezone.utc)


async def _user(session: AsyncSession, *, superuser: bool = False) -> User:
    user = User(
        email=f"u+{uuid.uuid4().hex[:8]}@test.local",
        is_active=True,
        is_superuser=superuser,
        hashed_password="x",
    )
    session.add(user)
    await session.flush()
    return user


async def _statuses(session: AsyncSession, *names: str) -> dict[str, uuid.UUID]:
    rows = [OrderStatus(name=name) for name in names]
    session.add_all(rows)
    await session.flush()
    return {row.name: row.id for row in rows}


def _order(
    user: User,
    status_id: uuid.UUID,
    *,
    total: str = "100",
    created_at: datetime = NOW,
    currency: str | None = None,
    departure: GroupedDeparture | None = None,
    is_active: bool = True,
) -> Order:
    return Order(
        user_id=user.id,
        order_status_id=status_id,
        total_amount=Decimal(total),
        currency=currency,
        created_at=created_at,
        grouped_departure_id=departure.id if departure else None,
        is_active=is_active,
    )


@pytest.mark.asyncio
async def test_empty_dashboard(db_session: AsyncSession) -> None:
    admin = await _user(db_session, superuser=True)
    await db_session.commit()

    result = await get_admin_dashboard(session=db_session, _admin=cast(Any, admin))

    assert result.todo.model_dump() == {
        "payments_to_validate": 0,
        "quote_requests_open": 0,
        "group_upgrade_requests_pending": 0,
        "orders_to_process": 0,
        "supplier_orders_draft": 0,
        "product_drafts": 0,
    }
    assert result.activity.currency == settings.REFERENCE_CURRENCY
    assert result.activity.orders_today == 0
    assert result.activity.orders_7d == 0
    assert result.activity.revenue_7d == Decimal(0)
    assert result.activity.revenue_30d == Decimal(0)
    assert result.activity.orders_30d == 0
    assert result.activity.average_basket_30d is None
    assert result.activity.carts_30d == 0
    assert result.activity.conversion_30d_pct is None
    assert result.stock.model_dump() == {
        "low_stock_threshold": 2,
        "low_stock": 0,
        "out_of_stock": 0,
    }
    assert result.next_departure is None


@pytest.mark.asyncio
async def test_todo_counters_match_their_screens(db_session: AsyncSession) -> None:
    admin = await _user(db_session, superuser=True)
    buyer = await _user(db_session)
    status = await _statuses(
        db_session, "Paid", "DepositPaid", "InTransit", "Pending", "Delivered"
    )

    # Payments: two waiting (cheque, purchase order), three that are not.
    awaiting = PaymentStatus(name="AwaitingValidation")
    under_review = PaymentStatus(name="UnderReview")
    completed = PaymentStatus(name="Completed")
    db_session.add_all([awaiting, under_review, completed])
    await db_session.flush()

    def payment(provider: str, status_id: uuid.UUID, **extra: Any) -> Payment:
        return Payment(
            user_id=buyer.id,
            amount=Decimal(10),
            provider_code=provider,
            payment_status_id=status_id,
            **extra,
        )

    # Orders: Paid + DepositPaid wait for the admin; the rest do not.
    orders = [
        _order(buyer, status["Paid"]),
        _order(buyer, status["DepositPaid"]),
        _order(buyer, status["Paid"], is_active=False),
        _order(buyer, status["InTransit"]),
        _order(buyer, status["Pending"]),
        _order(buyer, status["Delivered"]),
    ]
    group = PriceGroup(code="PRO", label="Pro", requires_validation=True)
    db_session.add_all([*orders, group])
    await db_session.flush()

    db_session.add_all(
        [
            payment("manual_check", awaiting.id),
            payment("po_public", under_review.id),
            payment("manual_check", completed.id),
            payment("payzen", awaiting.id),
            payment("manual_transfer", awaiting.id, is_active=False),
            QuoteRequest(email="a@test.local"),
            QuoteRequest(email="b@test.local", status="in_progress"),
            QuoteRequest(email="c@test.local", status="quoted"),
            QuoteRequest(email="d@test.local", status="won"),
            QuoteRequest(email="e@test.local", status="lost"),
            QuoteRequest(email="f@test.local", status="cancelled"),
            *(
                GroupUpgradeRequest(
                    user_id=buyer.id,
                    price_group_id=group.id,
                    business_registration_number=f"TAHITI-{i}",
                    status=s,
                )
                for i, s in enumerate(
                    [
                        UpgradeRequestStatus.pending,
                        UpgradeRequestStatus.pending,
                        UpgradeRequestStatus.approved,
                        UpgradeRequestStatus.rejected,
                    ]
                )
            ),
            *(
                SupplierOrder(
                    supplier_name="ingram_micro",
                    local_order_id=orders[0].id,
                    customer_order_number=f"PO-{s.value}",
                    status=s,
                )
                for s in SupplierOrderStatus
            ),
            Product(name="Brouillon 1", is_draft=True),
            Product(name="Brouillon 2", is_draft=True, is_active=False),
            Product(name="Publié", is_draft=False),
        ]
    )
    await db_session.commit()

    todo = (await build_dashboard(db_session, now=NOW)).todo

    assert todo.payments_to_validate == 2
    assert todo.quote_requests_open == 3
    assert todo.group_upgrade_requests_pending == 2
    assert todo.orders_to_process == 2
    assert todo.supplier_orders_draft == 2  # pending + error
    assert todo.product_drafts == 2

    # Same numbers as the screens the counters link to.
    pending = await list_pending_validation(session=db_session, _admin=cast(Any, admin))
    assert len(pending) == todo.payments_to_validate
    open_quotes = await list_quote_requests(
        session=db_session, _admin=cast(Any, admin), open_only=True
    )
    assert len(open_quotes) == todo.quote_requests_open


@pytest.mark.asyncio
async def test_activity_counts_sales_in_local_day_and_windows(
    db_session: AsyncSession,
) -> None:
    buyer = await _user(db_session)
    status = await _statuses(
        db_session, "Paid", "Delivered", "Pending", "Cancelled", "Refunded"
    )
    db_session.add(
        CurrencyRate(
            currency_code="EUR",
            rate_to_reference=Decimal("119.332"),
            valid_from=date(2020, 1, 1),
            source=CurrencyRateSource.manual,
        )
    )
    reference = settings.REFERENCE_CURRENCY
    db_session.add_all(
        [
            # Today, local time (after 10:00 UTC).
            _order(buyer, status["Paid"], total="1000", created_at=NOW),
            _order(
                buyer,
                status["Delivered"],
                total="500",
                currency=reference,
                created_at=NOW - timedelta(hours=1),
            ),
            # Yesterday evening in Tahiti, though the same UTC day.
            _order(
                buyer,
                status["Paid"],
                total="200",
                created_at=NOW - timedelta(hours=3),
            ),
            # In the 30-day window only; 10 EUR.
            _order(
                buyer,
                status["Paid"],
                total="10",
                currency="EUR",
                created_at=NOW - timedelta(days=12),
            ),
            # A currency without any rate: counted, not summed.
            _order(
                buyer,
                status["Paid"],
                total="99",
                currency="JPY",
                created_at=NOW - timedelta(days=2),
            ),
            # Not sales, or too old, or archived.
            _order(buyer, status["Pending"], total="7000", created_at=NOW),
            _order(buyer, status["Cancelled"], total="7000", created_at=NOW),
            _order(buyer, status["Refunded"], total="7000", created_at=NOW),
            _order(
                buyer, status["Paid"], total="7000", created_at=NOW - timedelta(days=31)
            ),
            _order(
                buyer, status["Paid"], total="7000", created_at=NOW, is_active=False
            ),
        ]
    )
    await db_session.commit()

    activity = (await build_dashboard(db_session, now=NOW)).activity

    assert activity.currency == reference
    assert activity.orders_today == 2
    assert activity.orders_7d == 4  # today ×2, yesterday evening, JPY
    assert activity.revenue_7d == Decimal("1700")
    assert activity.revenue_30d == Decimal("1700") + Decimal("1193.32")


@pytest.mark.asyncio
async def test_month_kpis_conversion_and_stock_watch(db_session: AsyncSession) -> None:
    """R8 / U7: average basket, cart conversion and the stock watch."""
    buyer = await _user(db_session)
    status = await _statuses(db_session, "Paid", "Pending")
    db_session.add_all(
        [
            _order(buyer, status["Paid"], total="1000", created_at=NOW),
            _order(
                buyer, status["Paid"], total="500", created_at=NOW - timedelta(days=20)
            ),
            # Not a sale, and a sale out of the window.
            _order(buyer, status["Pending"], total="9000", created_at=NOW),
            _order(
                buyer, status["Paid"], total="9000", created_at=NOW - timedelta(days=40)
            ),
        ]
    )

    def cart(*, days_ago: int, checked_out: bool = False) -> Cart:
        stamp = NOW - timedelta(days=days_ago)
        return Cart(
            user_id=buyer.id,
            currency=settings.REFERENCE_CURRENCY,
            is_checked_out=checked_out,
            created_at=stamp,
            last_activity_at=stamp,
        )

    db_session.add_all(
        [
            cart(days_ago=1, checked_out=True),
            cart(days_ago=5),
            cart(days_ago=29),
            cart(days_ago=45),  # too old
        ]
    )

    def product(name: str, **overrides: Any) -> Product:
        values: dict[str, Any] = {
            "name": name,
            "pricing_mode": PricingMode.FIXED,
            "base_price": Decimal("100"),
            "supplier_quantity": Decimal("0"),
        }
        values.update(overrides)
        return Product(**values)

    db_session.add_all(
        [
            # No supplier, no warehouse row: nothing sellable.
            product("Rupture"),
            # Supplier stock at the threshold (2) → low.
            product("Bas", supplier_name="tahiti", supplier_quantity=Decimal("2")),
            product("Plein", supplier_name="tahiti", supplier_quantity=Decimal("10")),
            # Pre-order: stock is not what is sold → not watched.
            product("Sur commande", availability_mode=AvailabilityMode.ON_DEMAND),
            # Not on the storefront.
            product("Brouillon", is_draft=True),
            product("Caché", is_admin_active=False),
        ]
    )
    await db_session.commit()

    result = await build_dashboard(db_session, now=NOW)

    assert result.activity.orders_30d == 2
    assert result.activity.average_basket_30d == Decimal("750")
    assert result.activity.carts_30d == 3
    assert result.activity.carts_ordered_30d == 1
    assert result.activity.conversion_30d_pct == Decimal("33.3")
    assert result.stock.low_stock_threshold == 2
    assert result.stock.out_of_stock == 1
    assert result.stock.low_stock == 1


@pytest.mark.asyncio
async def test_next_departure_prefers_open_then_draft(db_session: AsyncSession) -> None:
    buyer = await _user(db_session)
    status = await _statuses(db_session, "Paid", "Pending")

    def departure(name: str, state: str, days: int, **extra: Any) -> GroupedDeparture:
        return GroupedDeparture(
            name=name,
            status=state,
            order_cutoff_at=NOW + timedelta(days=days),
            **extra,
        )

    draft = departure("Décembre", "draft", 60)
    closed = departure("Septembre", "closed", -5)
    later_open = departure("Novembre", "open", 40)
    open_ = departure("Octobre", "open", 10, departure_at=NOW + timedelta(days=12))
    archived = departure("Ancien", "open", 1, is_active=False)
    db_session.add_all([draft, closed, later_open, open_, archived])
    await db_session.flush()
    db_session.add_all(
        [
            _order(buyer, status["Paid"], departure=open_),
            _order(buyer, status["Pending"], departure=open_),
            _order(buyer, status["Paid"], departure=later_open),
        ]
    )
    await db_session.commit()

    nxt = (await build_dashboard(db_session, now=NOW)).next_departure
    assert nxt is not None
    assert (nxt.id, nxt.label, nxt.status) == (open_.id, "Octobre", "open")
    assert nxt.cutoff_at == NOW + timedelta(days=10)
    assert nxt.departure_at == NOW + timedelta(days=12)
    assert nxt.orders_count == 2

    # With no open departure left, the next draft shows up.
    for d in (open_, later_open):
        d.status = "closed"
        db_session.add(d)
    await db_session.commit()
    nxt = (await build_dashboard(db_session, now=NOW)).next_departure
    assert nxt is not None
    assert (nxt.label, nxt.status, nxt.orders_count) == ("Décembre", "draft", 0)
