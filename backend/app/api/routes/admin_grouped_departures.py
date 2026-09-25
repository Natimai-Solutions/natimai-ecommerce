"""Admin management of grouped departures (« Départs groupés » screen).

The orders of a departure are read, exported and aggregated through the
filtered ``/admin/orders`` endpoints (``departure_id=…``); this router only
owns the departure itself and the attachment of orders to it.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from fastapi import APIRouter
from pydantic import BaseModel, Field
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.base.crud import RecordNotFoundError
from app.features.departure.crud import crud_grouped_departure, utcnow
from app.features.departure.models import (
    DepartureReminder,
    DepartureReminderPublic,
    DepartureReminderWrite,
    GroupedDeparture,
    GroupedDepartureCreate,
    GroupedDeparturePublic,
    GroupedDepartureUpdate,
    SupplierOrderEntry,
)
from app.features.departure.services import (
    CloseResult,
    add_default_reminders,
    add_reminder,
    close_departure,
    load_social_webhook_url,
    publish_reminder,
    reminder_fire_time,
    render_reminder,
    reschedule_reminders,
)
from app.features.order.services.status import propagate_departure_status

router = APIRouter(
    prefix="/admin/grouped-departures", tags=["admin-grouped-departures"]
)


class AssignOrdersRequest(BaseModel):
    """Attach orders to a departure, move them, or detach them (``null``)."""

    order_ids: list[uuid.UUID] = Field(min_length=1)
    departure_id: uuid.UUID | None = None


class AssignOrdersResponse(BaseModel):
    """Represents assign orders response."""

    updated: int


async def _get_or_404(session: SessionDep, departure_id: uuid.UUID) -> GroupedDeparture:
    try:
        departure: GroupedDeparture = await crud_grouped_departure.read(
            session, id=departure_id
        )
    except RecordNotFoundError as exc:
        raise AppError(
            code="grouped_departure.not_found",
            status_code=404,
            message="Départ groupé introuvable",
            details={"departure_id": str(departure_id)},
        ) from exc
    return departure


async def _to_public(
    session: SessionDep, departures: list[GroupedDeparture]
) -> list[GroupedDeparturePublic]:
    totals = await crud_grouped_departure.order_totals(
        session, (d.id for d in departures)
    )
    items = []
    for d in departures:
        item = GroupedDeparturePublic.model_validate(d)
        item.orders_count, item.orders_total = totals.get(d.id, (0, Decimal(0)))
        items.append(item)
    return items


@router.get("", response_model=list[GroupedDeparturePublic])
async def list_departures(
    session: SessionDep, _admin: CurrentSuperUser
) -> list[GroupedDeparturePublic]:
    """All departures, nearest cutoff first, with their order count and total."""
    departures = list(
        (
            await session.exec(
                select(GroupedDeparture)
                .where(col(GroupedDeparture.is_active).is_(True))
                .order_by(col(GroupedDeparture.order_cutoff_at).desc())
            )
        ).all()
    )
    return await _to_public(session, departures)


@router.post("", response_model=GroupedDeparturePublic, status_code=201)
async def create_departure(
    body: GroupedDepartureCreate, session: SessionDep, admin: CurrentSuperUser
) -> GroupedDeparturePublic:
    """Create a departure with its default reminders (J-7, J-2, last day)."""
    departure = await crud_grouped_departure.create(session, data=body, user=admin)
    departure_id = departure.id
    await add_default_reminders(session, departure)
    await session.commit()
    departure = await _get_or_404(session, departure_id)
    return (await _to_public(session, [departure]))[0]


@router.patch("/{departure_id}", response_model=GroupedDeparturePublic)
async def update_departure(
    departure_id: uuid.UUID,
    body: GroupedDepartureUpdate,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> GroupedDeparturePublic:
    """Partial update: dates, publication, status, thresholds, notes.

    A status change is pushed to the orders that follow the departure
    (paid or already on the way) and each one e-mails its customer.
    """
    departure = await _get_or_404(session, departure_id)
    previous_status = departure.status
    admin_id = admin.id
    departure = await crud_grouped_departure.update(
        session,
        id=departure_id,
        data=body.model_dump(exclude_unset=True),
        user=admin,
        record=departure,
    )
    fields = body.model_dump(exclude_unset=True)
    if "order_cutoff_at" in fields or "departure_at" in fields:
        await reschedule_reminders(session, departure)
        await session.commit()
        departure = await _get_or_404(session, departure_id)
    orders_updated = 0
    if departure.status != previous_status:
        orders_updated = await propagate_departure_status(
            session,
            departure_id=departure_id,
            departure_status=departure.status,
            changed_by_id=admin_id,
        )
        await session.commit()
        departure = await _get_or_404(session, departure_id)
    result = (await _to_public(session, [departure]))[0]
    result.orders_updated = orders_updated
    return result


@router.delete("/{departure_id}", response_model=AssignOrdersResponse)
async def delete_departure(
    departure_id: uuid.UUID, session: SessionDep, admin: CurrentSuperUser
) -> AssignOrdersResponse:
    """Delete a departure that has no order attached (409 otherwise: move the
    orders first, the attachment is part of the customer's promise)."""
    departure = await _get_or_404(session, departure_id)
    totals = await crud_grouped_departure.order_totals(session, [departure_id])
    attached = totals.get(departure_id, (0, 0.0))[0]
    if attached:
        raise AppError(
            code="grouped_departure.has_orders",
            status_code=409,
            message="Des commandes sont rattachées à ce départ : déplacez-les d'abord",
            details={"departure_id": str(departure_id), "orders_count": attached},
        )
    # Its reminders go with it (never posted: the departure no longer exists).
    for reminder in (
        await session.exec(
            select(DepartureReminder).where(
                col(DepartureReminder.grouped_departure_id) == departure_id
            )
        )
    ).all():
        await session.delete(reminder)
    await session.flush()
    await crud_grouped_departure.delete(
        session, id=departure_id, record=departure, user=admin
    )
    return AssignOrdersResponse(updated=0)


@router.post("/assign-orders", response_model=AssignOrdersResponse)
async def assign_orders(
    body: AssignOrdersRequest, session: SessionDep, _admin: CurrentSuperUser
) -> AssignOrdersResponse:
    """Attach / move / detach orders. Unknown order ids are ignored."""
    if body.departure_id is not None:
        await _get_or_404(session, body.departure_id)
    updated = await crud_grouped_departure.assign_orders(
        session, order_ids=body.order_ids, departure_id=body.departure_id
    )
    return AssignOrdersResponse(updated=updated)


# --- Assisted close ---------------------------------------------------------


class CloseRequest(BaseModel):
    """``force`` closes even when a minimum threshold is not reached."""

    force: bool = False


@router.post("/{departure_id}/close", response_model=CloseResult)
async def close_departure_endpoint(
    departure_id: uuid.UUID,
    body: CloseRequest,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> CloseResult:
    """Close the departure: live supplier stock check on every ordered
    product, thresholds, next departure when recurring. The result lists what
    is left to arbitrate (shortages, unpaid orders)."""
    departure = await _get_or_404(session, departure_id)
    if departure.status not in ("draft", "open"):
        raise AppError(
            code="grouped_departure.not_open",
            status_code=409,
            message="Ce départ est déjà clôturé",
            details={"departure_id": str(departure_id), "status": departure.status},
        )
    result = await close_departure(session, departure=departure, force=body.force)
    await session.commit()
    return result


# --- Supplier purchase orders recorded on the departure ---------------------


@router.post("/{departure_id}/supplier-orders", response_model=GroupedDeparturePublic)
async def add_supplier_order(
    departure_id: uuid.UUID,
    body: SupplierOrderEntry,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> GroupedDeparturePublic:
    """Record the real purchase order placed with a supplier (number, date,
    amount). The first one moves the departure to « ordered » (and its
    orders to « commandée au fournisseur »)."""
    departure = await _get_or_404(session, departure_id)
    entries = list(departure.supplier_orders or [])
    entries.append(body.model_dump(mode="json"))
    departure.supplier_orders = entries
    session.add(departure)
    orders_updated = 0
    if departure.status in ("draft", "open", "closed"):
        departure.status = "ordered"
        orders_updated = await propagate_departure_status(
            session,
            departure_id=departure_id,
            departure_status="ordered",
            changed_by_id=admin.id,
        )
    await session.commit()
    departure = await _get_or_404(session, departure_id)
    result = (await _to_public(session, [departure]))[0]
    result.orders_updated = orders_updated
    return result


@router.delete(
    "/{departure_id}/supplier-orders/{index}", response_model=GroupedDeparturePublic
)
async def remove_supplier_order(
    departure_id: uuid.UUID, index: int, session: SessionDep, _admin: CurrentSuperUser
) -> GroupedDeparturePublic:
    """Remove a recorded purchase order (typo, wrong supplier)."""
    departure = await _get_or_404(session, departure_id)
    entries = list(departure.supplier_orders or [])
    if not 0 <= index < len(entries):
        raise AppError(
            code="grouped_departure.supplier_order.not_found",
            status_code=404,
            message="Bon de commande introuvable",
            details={"index": index},
        )
    entries.pop(index)
    departure.supplier_orders = entries or None
    session.add(departure)
    await session.commit()
    departure = await _get_or_404(session, departure_id)
    return (await _to_public(session, [departure]))[0]


# --- Reminders --------------------------------------------------------------


async def _reminder_or_404(
    session: SessionDep, reminder_id: uuid.UUID
) -> tuple[DepartureReminder, GroupedDeparture]:
    reminder = await session.get(DepartureReminder, reminder_id)
    if reminder is None or not reminder.is_active:
        raise AppError(
            code="departure_reminder.not_found",
            status_code=404,
            message="Rappel introuvable",
            details={"reminder_id": str(reminder_id)},
        )
    departure = await _get_or_404(session, reminder.grouped_departure_id)
    return reminder, departure


def _reminder_public(
    reminder: DepartureReminder, departure: GroupedDeparture
) -> DepartureReminderPublic:
    item = DepartureReminderPublic.model_validate(reminder)
    item.rendered_text = render_reminder(reminder, departure, now=utcnow())
    return item


@router.get("/{departure_id}/reminders", response_model=list[DepartureReminderPublic])
async def list_reminders(
    departure_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> list[DepartureReminderPublic]:
    """Reminders of a departure, soonest first, with the text as it will post."""
    departure = await _get_or_404(session, departure_id)
    rows = (
        await session.exec(
            select(DepartureReminder)
            .where(
                col(DepartureReminder.grouped_departure_id) == departure_id,
                col(DepartureReminder.is_active).is_(True),
            )
            .order_by(col(DepartureReminder.scheduled_at).asc())
        )
    ).all()
    return [_reminder_public(r, departure) for r in rows]


@router.post(
    "/{departure_id}/reminders",
    response_model=DepartureReminderPublic,
    status_code=201,
)
async def create_reminder(
    departure_id: uuid.UUID,
    body: DepartureReminderWrite,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> DepartureReminderPublic:
    """Schedule a reminder N days before the cutoff (or the departure)."""
    departure = await _get_or_404(session, departure_id)
    reminder_id = (await add_reminder(session, departure, body)).id  # before commit
    await session.commit()
    reminder, departure = await _reminder_or_404(session, reminder_id)
    return _reminder_public(reminder, departure)


@router.patch("/reminders/{reminder_id}", response_model=DepartureReminderPublic)
async def update_reminder(
    reminder_id: uuid.UUID,
    body: DepartureReminderWrite,
    session: SessionDep,
    _admin: CurrentSuperUser,
) -> DepartureReminderPublic:
    """Edit a reminder that has not fired yet; it is rescheduled."""
    reminder, departure = await _reminder_or_404(session, reminder_id)
    for key, value in body.model_dump().items():
        setattr(reminder, key, value)
    reminder.scheduled_at = reminder_fire_time(
        departure, offset_days=body.offset_days, anchor=body.anchor
    )
    if reminder.status != "sent":
        reminder.status = "scheduled"
        reminder.error = None
    session.add(reminder)
    await session.commit()
    reminder, departure = await _reminder_or_404(session, reminder_id)
    return _reminder_public(reminder, departure)


@router.delete("/reminders/{reminder_id}", response_model=AssignOrdersResponse)
async def delete_reminder(
    reminder_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> AssignOrdersResponse:
    """Drop a reminder (soft)."""
    reminder, _departure = await _reminder_or_404(session, reminder_id)
    reminder.is_active = False
    reminder.status = "cancelled"
    session.add(reminder)
    await session.commit()
    return AssignOrdersResponse(updated=1)


@router.post("/reminders/{reminder_id}/publish", response_model=DepartureReminderPublic)
async def publish_reminder_now(
    reminder_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> DepartureReminderPublic:
    """Post the reminder right now, whatever its schedule."""
    reminder, departure = await _reminder_or_404(session, reminder_id)
    await publish_reminder(
        session,
        reminder,
        departure,
        now=utcnow(),
        webhook_url=await load_social_webhook_url(session),
    )
    await session.commit()
    reminder, departure = await _reminder_or_404(session, reminder_id)
    return _reminder_public(reminder, departure)
