"""Back-office view of open carts and the abandoned-cart reminder (Z3)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.config import settings
from app.features.cart.services.abandonment import open_carts_overview

router = APIRouter(prefix="/admin/carts", tags=["admin-cart"])


class AbandonedCartsResponse(BaseModel):
    """Open carts with their owner, plus the reminder counters."""

    data: list[dict[str, Any]] = Field(default_factory=list)
    counters: dict[str, int] = Field(default_factory=dict)
    reminder_delay_hours: int
    reminder_max_age_days: int


@router.get("/abandoned", response_model=AbandonedCartsResponse)
async def list_abandoned_carts(
    session: SessionDep,
    _admin: CurrentSuperUser,
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=200),
) -> AbandonedCartsResponse:
    """Open carts (never ordered, with lines), most recent activity first.

    « Récupérés » counts the reminded carts that were ordered since: the one
    number that tells whether the reminder pays.
    """
    page, counters = await open_carts_overview(session, skip=skip, limit=limit)
    return AbandonedCartsResponse(
        data=page,
        counters=counters,
        reminder_delay_hours=int(settings.CART_ABANDONMENT_REMINDER_DELAY_HOURS),
        reminder_max_age_days=int(settings.CART_ABANDONMENT_MAX_AGE_DAYS),
    )
