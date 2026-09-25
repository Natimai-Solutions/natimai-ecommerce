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
from app.features.departure.crud import crud_grouped_departure
from app.features.departure.models import (
    GroupedDeparture,
    GroupedDepartureCreate,
    GroupedDeparturePublic,
    GroupedDepartureUpdate,
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
    """Create a departure (open + published by default from the admin form)."""
    departure = await crud_grouped_departure.create(session, data=body, user=admin)
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
