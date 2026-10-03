"""Grouped departure workflows: assisted close, recurrence, reminders.

Everything here works on an open session and never commits, except where
documented; the endpoints and the cron task own the transactions.
"""

from __future__ import annotations

import logging
import uuid
from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from typing import Any
from zoneinfo import ZoneInfo

from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from app.core.config import settings
from app.core.webhook import post_json
from app.features.departure.crud import crud_grouped_departure, utcnow
from app.features.departure.models import (
    DEFAULT_REMINDERS,
    DepartureReminder,
    DepartureReminderWrite,
    GroupedDeparture,
)
from app.features.integrations.services.checkout_availability import (
    refresh_supplier_availability,
)
from app.features.order.models.order import Order
from app.features.order.models.order_line import OrderLine
from app.features.order.models.order_status import OrderStatus
from app.features.order.services.status import DEPARTURE_FOLLOWER_STATUSES
from app.features.product.models.product import Product

logger = logging.getLogger(__name__)

SOCIAL_WEBHOOK_SETTING_KEY = "social_webhook_url"
LOCAL_TZ = ZoneInfo("Pacific/Tahiti")
REMINDER_HOUR = time(9, 0)


# --- Assisted close ---------------------------------------------------------


class Shortage(BaseModel):
    """A product the supplier can no longer serve in full at close time."""

    product_id: uuid.UUID
    product_name: str
    supplier_name: str | None
    supplier_sku: str | None
    ordered_quantity: int
    available_quantity: int
    order_ids: list[uuid.UUID]
    order_numbers: list[str | None]


class CloseResult(BaseModel):
    """What the admin has to arbitrate after a close."""

    departure_id: uuid.UUID
    closed: bool
    orders_count: int
    orders_total: Decimal
    threshold_reached: bool
    shortages: list[Shortage]
    unpaid_order_ids: list[uuid.UUID]
    next_departure_id: uuid.UUID | None = None


async def _attached_orders(
    session: AsyncSession, departure_id: uuid.UUID
) -> list[tuple[Order, str | None]]:
    rows = (
        await session.exec(
            select(Order, OrderStatus.name)
            .join(OrderStatus, col(OrderStatus.id) == col(Order.order_status_id))
            .where(
                col(Order.grouped_departure_id) == departure_id,
                col(Order.is_active).is_(True),
            )
        )
    ).all()
    return [(order, name) for order, name in rows]


async def find_shortages(session: AsyncSession, orders: list[Order]) -> list[Shortage]:
    """Refresh the supplier stock of every product ordered and report the
    products whose live quantity does not cover the total ordered.

    Only products the supplier actually answered for are compared (a product
    reserved from a lot or a local stock has no live quantity to check).
    """
    if not orders:
        return []
    order_ids = [o.id for o in orders]
    lines = (
        await session.exec(
            select(OrderLine).where(
                col(OrderLine.order_id).in_(order_ids),
                col(OrderLine.is_active).is_(True),
            )
        )
    ).all()
    ordered: dict[uuid.UUID, int] = {}
    by_product_orders: dict[uuid.UUID, set[uuid.UUID]] = {}
    for line in lines:
        ordered[line.product_id] = ordered.get(line.product_id, 0) + int(line.quantity)
        by_product_orders.setdefault(line.product_id, set()).add(line.order_id)
    if not ordered:
        return []
    products = list(
        (
            await session.exec(
                select(Product).where(col(Product.id).in_(list(ordered)))
            )
        ).all()
    )
    live = await refresh_supplier_availability(session, products)
    numbers = {o.id: o.order_number for o in orders}
    shortages: list[Shortage] = []
    for product in products:
        sku = str(product.supplier_sku or "")
        if sku not in live:
            continue
        available = int(live[sku])
        needed = ordered[product.id]
        if available >= needed:
            continue
        ids = sorted(by_product_orders[product.id], key=lambda i: str(i))
        shortages.append(
            Shortage(
                product_id=product.id,
                product_name=product.name,
                supplier_name=product.supplier_name,
                supplier_sku=product.supplier_sku,
                ordered_quantity=needed,
                available_quantity=available,
                order_ids=ids,
                order_numbers=[numbers.get(i) for i in ids],
            )
        )
    return shortages


def threshold_reached(
    departure: GroupedDeparture, *, total: Decimal, units: int
) -> bool:
    """Optional minimums: both must be met when set."""
    if departure.min_amount is not None and total < departure.min_amount:
        return False
    return not (departure.min_units is not None and units < departure.min_units)


async def close_departure(
    session: AsyncSession,
    *,
    departure: GroupedDeparture,
    force: bool = False,
) -> CloseResult:
    """Close a departure: live stock check, thresholds, recurrence.

    Without ``force`` the departure stays open when a threshold is not met
    (the admin sees the numbers and decides). Does not commit.
    """
    attached = await _attached_orders(session, departure.id)
    followers = [o for o, name in attached if name in DEPARTURE_FOLLOWER_STATUSES]
    unpaid = [o.id for o, name in attached if name not in DEPARTURE_FOLLOWER_STATUSES]
    total = sum((o.total_amount for o in followers), Decimal(0))
    units = 0
    if followers:
        units = int(
            sum(
                int(line.quantity)
                for line in (
                    await session.exec(
                        select(OrderLine).where(
                            col(OrderLine.order_id).in_([o.id for o in followers]),
                            col(OrderLine.is_active).is_(True),
                        )
                    )
                ).all()
            )
        )
    reached = threshold_reached(departure, total=total, units=units)
    shortages = await find_shortages(session, followers)

    closed = reached or force
    next_id: uuid.UUID | None = None
    if closed and departure.status in ("draft", "open"):
        departure.status = "closed"
        departure.is_published = False
        session.add(departure)
        if departure.recurrence_days:
            next_id = (await spawn_next_departure(session, departure)).id

    return CloseResult(
        departure_id=departure.id,
        closed=closed,
        orders_count=len(followers),
        orders_total=total,
        threshold_reached=reached,
        shortages=shortages,
        unpaid_order_ids=unpaid,
        next_departure_id=next_id,
    )


async def spawn_next_departure(
    session: AsyncSession, departure: GroupedDeparture
) -> GroupedDeparture:
    """The following departure of a recurring one: same settings, dates
    shifted by ``recurrence_days``, reminders copied, open and published."""
    shift = timedelta(days=int(departure.recurrence_days or 0))
    nxt = GroupedDeparture(
        name=f"{departure.name} (suivant)",
        order_cutoff_at=departure.order_cutoff_at + shift,
        estimated_delivery_at=(
            departure.estimated_delivery_at + shift
            if departure.estimated_delivery_at
            else None
        ),
        departure_at=departure.departure_at + shift if departure.departure_at else None,
        status="open",
        is_published=True,
        min_amount=departure.min_amount,
        min_units=departure.min_units,
        recurrence_days=departure.recurrence_days,
        notes=departure.notes,
    )
    session.add(nxt)
    await session.flush()
    reminders = (
        await session.exec(
            select(DepartureReminder).where(
                col(DepartureReminder.grouped_departure_id) == departure.id,
                col(DepartureReminder.is_active).is_(True),
            )
        )
    ).all()
    for reminder in reminders:
        await add_reminder(
            session,
            nxt,
            DepartureReminderWrite(
                offset_days=reminder.offset_days,
                anchor=reminder.anchor,
                channel=reminder.channel,
                message_template=reminder.message_template,
                image_url=reminder.image_url,
            ),
        )
    return nxt


# --- Reminders --------------------------------------------------------------


def reminder_fire_time(
    departure: GroupedDeparture, *, offset_days: int, anchor: str
) -> datetime:
    """``anchor − offset`` days, at 09:00 local time (Tahiti)."""
    base = departure.order_cutoff_at
    if anchor == "departure" and departure.departure_at:
        base = departure.departure_at
    local_day = base.astimezone(LOCAL_TZ).date() - timedelta(days=offset_days)
    return datetime.combine(local_day, REMINDER_HOUR, tzinfo=LOCAL_TZ).astimezone(UTC)


def render_reminder(
    reminder: DepartureReminder, departure: GroupedDeparture, *, now: datetime
) -> str:
    """Fill the template; an unknown placeholder is left as typed."""
    cutoff_local = departure.order_cutoff_at.astimezone(LOCAL_TZ)
    days_left = max(0, (cutoff_local.date() - now.astimezone(LOCAL_TZ).date()).days)
    values = {
        "name": departure.name,
        "cutoff_date": cutoff_local.strftime("%d/%m/%Y"),
        "days_left": str(days_left),
        "delivery_date": (
            departure.estimated_delivery_at.astimezone(LOCAL_TZ).strftime("%d/%m/%Y")
            if departure.estimated_delivery_at
            else "à confirmer"
        ),
        "shop_url": settings.FRONTEND_HOST,
    }
    text = reminder.message_template
    for key, value in values.items():
        text = text.replace("{" + key + "}", value)
    return text


async def add_reminder(
    session: AsyncSession, departure: GroupedDeparture, data: DepartureReminderWrite
) -> DepartureReminder:
    """Schedule a reminder on a departure (flushes, no commit)."""
    reminder = DepartureReminder(
        grouped_departure_id=departure.id,
        scheduled_at=reminder_fire_time(
            departure, offset_days=data.offset_days, anchor=data.anchor
        ),
        **data.model_dump(),
    )
    session.add(reminder)
    await session.flush()
    return reminder


async def add_default_reminders(
    session: AsyncSession, departure: GroupedDeparture
) -> list[DepartureReminder]:
    """J-7, J-2 and last-day reminders (only those still in the future)."""
    now = utcnow()
    created: list[DepartureReminder] = []
    for offset, template in DEFAULT_REMINDERS:
        if reminder_fire_time(departure, offset_days=offset, anchor="cutoff") <= now:
            continue
        created.append(
            await add_reminder(
                session,
                departure,
                DepartureReminderWrite(offset_days=offset, message_template=template),
            )
        )
    return created


async def reschedule_reminders(
    session: AsyncSession, departure: GroupedDeparture
) -> int:
    """Recompute the fire time of the pending reminders after a date change."""
    pending = (
        await session.exec(
            select(DepartureReminder).where(
                col(DepartureReminder.grouped_departure_id) == departure.id,
                col(DepartureReminder.status) == "scheduled",
                col(DepartureReminder.is_active).is_(True),
            )
        )
    ).all()
    for reminder in pending:
        reminder.scheduled_at = reminder_fire_time(
            departure, offset_days=reminder.offset_days, anchor=reminder.anchor
        )
        session.add(reminder)
    return len(pending)


async def load_social_webhook_url(session: AsyncSession) -> str | None:
    from app.core import runtime_settings

    value = str(await runtime_settings.get(SOCIAL_WEBHOOK_SETTING_KEY, session) or "")
    return value.strip() or None


async def publish_reminder(
    session: AsyncSession,
    reminder: DepartureReminder,
    departure: GroupedDeparture,
    *,
    now: datetime,
    webhook_url: str | None,
) -> bool:
    """Post one reminder and record the outcome (flushes, no commit)."""
    text = render_reminder(reminder, departure, now=now)
    payload: dict[str, Any] = {
        "text": text,
        "link": settings.FRONTEND_HOST,
        "image_url": reminder.image_url,
        "departure": {
            "id": str(departure.id),
            "name": departure.name,
            "order_cutoff_at": departure.order_cutoff_at.isoformat(),
        },
    }
    delivered, error = (
        await post_json(webhook_url, payload)
        if webhook_url
        else (False, "Aucune URL de webhook configurée")
    )
    reminder.status = "sent" if delivered else "failed"
    reminder.sent_at = now if delivered else None
    reminder.error = error
    session.add(reminder)
    await session.flush()
    return delivered


async def publish_due_reminders(
    session: AsyncSession, *, now: datetime | None = None
) -> dict[str, int]:
    """Post every scheduled reminder whose time has come (cron entry point).

    A departure that is no longer open and published stops its reminders
    (cancelled), so a closed or hidden departure is never advertised.
    Commits.
    """
    now = now or utcnow()
    due = (
        await session.exec(
            select(DepartureReminder, GroupedDeparture)
            .join(
                GroupedDeparture,
                col(GroupedDeparture.id) == col(DepartureReminder.grouped_departure_id),
            )
            .where(
                col(DepartureReminder.status) == "scheduled",
                col(DepartureReminder.is_active).is_(True),
                col(DepartureReminder.scheduled_at) <= now,
            )
        )
    ).all()
    webhook_url = await load_social_webhook_url(session)
    sent = failed = cancelled = 0
    for reminder, departure in due:
        if departure.status != "open" or not departure.is_published:
            reminder.status = "cancelled"
            reminder.error = "départ fermé ou non publié"
            session.add(reminder)
            cancelled += 1
            continue
        if await publish_reminder(
            session, reminder, departure, now=now, webhook_url=webhook_url
        ):
            sent += 1
        else:
            failed += 1
    await session.commit()
    if failed:
        logger.warning("Departure reminders: %d failed to post", failed)
    return {"sent": sent, "failed": failed, "cancelled": cancelled}


__all__ = [
    "CloseResult",
    "Shortage",
    "add_default_reminders",
    "add_reminder",
    "close_departure",
    "crud_grouped_departure",
    "find_shortages",
    "publish_due_reminders",
    "publish_reminder",
    "reminder_fire_time",
    "render_reminder",
    "reschedule_reminders",
    "spawn_next_departure",
    "threshold_reached",
]
