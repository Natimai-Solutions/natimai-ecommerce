"""Admin home page (« À traiter » work queue and a glimpse of activity).

``GET /admin/dashboard`` answers one question: what is waiting for the admin
right now. Every counter reuses the definition of the screen it links to, so
the number on the home page is the number of rows the admin finds there:

- ``payments_to_validate``: « Validation paiements » — manual payments
  (cheque, transfer…) awaiting validation and purchase-order payments whose
  document is uploaded or under review (``pending_validation_conditions``).
- ``quote_requests_open``: « Demandes de devis » with ``open_only=true`` —
  every request not won, lost or cancelled (``CLOSED_QUOTE_STATUSES``).
- ``group_upgrade_requests_pending``: « Demandes de passage pro » (default
  ``pending_only=true``) — requests in ``PENDING``.
- ``orders_to_process``: active orders in ``Paid`` or ``DepositPaid``
  (``ORDERS_TO_PROCESS_STATUSES``): paid, no fulfilment step taken yet.
- ``supplier_orders_draft``: supplier purchase orders not transmitted to the
  supplier — ``pending`` (not sent yet) or ``error`` (the call failed and
  waits for a manual retry). ``submitted`` and ``skipped`` need nothing.
- ``product_drafts``: products imported as drafts by a supplier sync or file
  import (``Product.is_draft``), the « Brouillons (à publier) » filter of the
  product list.

Activity counts the orders that count as sales for the grouped-departure
dashboard (``RECEIVABLE_STATUSES``: paid, on the way or handed over — neither
unpaid, failed, refunded nor cancelled), by creation date. « Today » starts at
local midnight in the shop's time zone (``LOCAL_TZ``, the one the departure
reminders use); the 7- and 30-day windows are rolling. Revenue is the sum of
the order totals converted to the reference currency; a currency without an
active rate is left out (and logged) rather than summed as if it were XPF.

Only COUNT / SUM queries: the cost does not grow with the number of rows.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, time, timedelta
from decimal import Decimal
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel
from sqlalchemy import case, func
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.config import settings
from app.core.datetimes import utcnow
from app.features.cart.models.quote_request import CLOSED_QUOTE_STATUSES, QuoteRequest
from app.features.departure.crud import crud_grouped_departure
from app.features.departure.models import GroupedDeparture
from app.features.departure.reception import RECEIVABLE_STATUSES
from app.features.departure.services import LOCAL_TZ
from app.features.integrations.models.supplier_order import (
    SupplierOrder,
    SupplierOrderStatus,
)
from app.features.order.models.order import Order
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.status import ORDERS_TO_PROCESS_STATUSES
from app.features.payment.models.payment import Payment
from app.features.payment.services.pending_validation import (
    pending_validation_conditions,
)
from app.features.product.models.product import Product
from app.features.product.services.pricing import (
    CurrencyRateMissing,
    convert_to_reference_currency,
)
from app.features.user.models.group_upgrade_request import (
    GroupUpgradeRequest,
    UpgradeRequestStatus,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin/dashboard", tags=["admin-dashboard"])

#: Supplier purchase orders not transmitted to the supplier yet.
SUPPLIER_ORDER_TODO_STATUSES: tuple[SupplierOrderStatus, ...] = (
    SupplierOrderStatus.PENDING,
    SupplierOrderStatus.ERROR,
)
#: Departures still ahead: taking orders, or being prepared.
UPCOMING_DEPARTURE_STATUSES: tuple[str, ...] = ("open", "draft")


class DashboardTodo(BaseModel):
    """Work queue: how many items wait for an admin action, per screen."""

    payments_to_validate: int = 0
    quote_requests_open: int = 0
    group_upgrade_requests_pending: int = 0
    orders_to_process: int = 0
    supplier_orders_draft: int = 0
    product_drafts: int = 0


class DashboardActivity(BaseModel):
    """Orders and revenue (reference currency) over recent windows."""

    currency: str
    orders_today: int = 0
    orders_7d: int = 0
    revenue_7d: Decimal = Decimal("0")
    revenue_30d: Decimal = Decimal("0")


class DashboardDeparture(BaseModel):
    """The next grouped departure: the open one, else the next draft."""

    id: uuid.UUID
    label: str
    status: str
    cutoff_at: datetime | None = None
    departure_at: datetime | None = None
    orders_count: int = 0


class AdminDashboard(BaseModel):
    """Admin home page payload."""

    todo: DashboardTodo
    activity: DashboardActivity
    next_departure: DashboardDeparture | None = None


async def _count(session: AsyncSession, model: Any, *conditions: Any) -> int:
    statement = select(func.count()).select_from(model).where(*conditions)
    return int((await session.exec(statement)).one())


def _status_ids(names: frozenset[str]) -> Any:
    return select(OrderStatus.id).where(col(OrderStatus.name).in_(names))


async def _todo(session: AsyncSession) -> DashboardTodo:
    payment_conditions = await pending_validation_conditions(session)
    return DashboardTodo(
        payments_to_validate=(
            await _count(session, Payment, *payment_conditions)
            if payment_conditions is not None
            else 0
        ),
        quote_requests_open=await _count(
            session,
            QuoteRequest,
            col(QuoteRequest.status).notin_([s.value for s in CLOSED_QUOTE_STATUSES]),
        ),
        group_upgrade_requests_pending=await _count(
            session,
            GroupUpgradeRequest,
            col(GroupUpgradeRequest.status) == UpgradeRequestStatus.pending,
        ),
        orders_to_process=await _count(
            session,
            Order,
            col(Order.is_active).is_(True),
            col(Order.order_status_id).in_(_status_ids(ORDERS_TO_PROCESS_STATUSES)),
        ),
        supplier_orders_draft=await _count(
            session,
            SupplierOrder,
            col(SupplierOrder.status).in_(SUPPLIER_ORDER_TODO_STATUSES),
        ),
        product_drafts=await _count(session, Product, col(Product.is_draft).is_(True)),
    )


async def _activity(session: AsyncSession, now: datetime) -> DashboardActivity:
    reference = settings.REFERENCE_CURRENCY
    local_midnight = datetime.combine(
        now.astimezone(LOCAL_TZ).date(), time.min, tzinfo=LOCAL_TZ
    )
    since_7d = now - timedelta(days=7)
    since_30d = now - timedelta(days=30)
    created_at = col(Order.created_at)
    # Each order falls in the narrowest window it belongs to; the wider
    # windows add the narrower ones up.
    window = case(
        (created_at >= local_midnight, "today"),
        (created_at >= since_7d, "7d"),
        else_="30d",
    )
    statement = (
        select(
            col(Order.currency),
            window,
            func.count(),
            func.coalesce(func.sum(col(Order.total_amount)), 0),
        )
        .where(
            col(Order.is_active).is_(True),
            col(Order.order_status_id).in_(_status_ids(RECEIVABLE_STATUSES)),
            created_at >= since_30d,
        )
        .group_by(col(Order.currency), window)
    )
    rows = (await session.exec(statement)).all()

    activity = DashboardActivity(currency=reference)
    for currency, bucket, count, amount in rows:
        if bucket in ("today", "7d"):
            activity.orders_7d += int(count)
        if bucket == "today":
            activity.orders_today += int(count)
        try:
            converted, _rate = await convert_to_reference_currency(
                session, Decimal(amount), currency or reference
            )
        except CurrencyRateMissing:
            logger.warning(
                "Dashboard revenue: no active %s rate to %s, orders left out",
                currency,
                reference,
            )
            continue
        activity.revenue_30d += converted
        if bucket in ("today", "7d"):
            activity.revenue_7d += converted
    return activity


async def _next_departure(session: AsyncSession) -> DashboardDeparture | None:
    """The open departure with the nearest cutoff (even past: it then waits to
    be closed), else the draft one with the nearest cutoff."""
    departure = (
        await session.exec(
            select(GroupedDeparture)
            .where(
                col(GroupedDeparture.is_active).is_(True),
                col(GroupedDeparture.status).in_(UPCOMING_DEPARTURE_STATUSES),
            )
            .order_by(
                case((col(GroupedDeparture.status) == "open", 0), else_=1),
                col(GroupedDeparture.order_cutoff_at).asc(),
            )
            .limit(1)
        )
    ).first()
    if departure is None:
        return None
    totals = await crud_grouped_departure.order_totals(session, [departure.id])
    orders_count, _total = totals.get(departure.id, (0, Decimal(0)))
    return DashboardDeparture(
        id=departure.id,
        label=departure.name,
        status=departure.status,
        cutoff_at=departure.order_cutoff_at,
        departure_at=departure.departure_at,
        orders_count=orders_count,
    )


async def build_dashboard(
    session: AsyncSession, *, now: datetime | None = None
) -> AdminDashboard:
    """Assemble the dashboard; ``now`` is injectable for tests."""
    moment = now or utcnow()
    return AdminDashboard(
        todo=await _todo(session),
        activity=await _activity(session, moment),
        next_departure=await _next_departure(session),
    )


@router.get("", response_model=AdminDashboard)
async def get_admin_dashboard(
    session: SessionDep, _admin: CurrentSuperUser
) -> AdminDashboard:
    """Work queue counters, recent activity and the next grouped departure."""
    return await build_dashboard(session)
