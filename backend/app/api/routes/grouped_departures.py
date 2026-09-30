"""Public (no auth) view of grouped departures for the storefront.

``/next`` feeds the banner, the product page and the checkout; ``/{id}`` lets
the order confirmation and the customer account show the departure an order is
attached to. Only published departures are exposed, and only the customer-facing
fields (``GroupedDepartureSummary``).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlmodel import col, select

from app.api.deps import SessionDep
from app.core.errors import AppError
from app.features.departure.crud import crud_grouped_departure
from app.features.departure.models import GroupedDeparture, GroupedDepartureSummary
from app.features.system.modules import module_enabled

router = APIRouter(prefix="/grouped-departures", tags=["grouped-departures"])


@router.get("/next", response_model=GroupedDepartureSummary | None)
async def next_departure(session: SessionDep) -> GroupedDepartureSummary | None:
    """The departure new orders are attached to right now, or ``null``
    (always ``null`` while the grouped-departures module is off)."""
    if not await module_enabled(session, "grouped_departures"):
        return None
    departure = await crud_grouped_departure.get_next_open(session)
    return GroupedDepartureSummary.model_validate(departure) if departure else None


@router.get("/{departure_id}", response_model=GroupedDepartureSummary)
async def get_departure(
    departure_id: uuid.UUID, session: SessionDep
) -> GroupedDepartureSummary:
    """A published departure (any status): the customer follows their order's
    departure until it is distributed."""
    departure = (
        await session.exec(
            select(GroupedDeparture).where(
                col(GroupedDeparture.id) == departure_id,
                col(GroupedDeparture.is_active).is_(True),
                col(GroupedDeparture.is_published).is_(True),
            )
        )
    ).first()
    if departure is None:
        raise AppError(
            code="grouped_departure.not_found",
            status_code=404,
            message="Départ groupé introuvable",
            details={"departure_id": str(departure_id)},
        )
    return GroupedDepartureSummary.model_validate(departure)
