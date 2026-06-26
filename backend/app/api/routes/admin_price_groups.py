"""Admin endpoint: read-only listing of price groups.

Supports the back-office screens that need to reference price groups by id —
payment-method eligibility and direct group assignment — since the existing
eligibility endpoint only returns the groups already attached to a method.
"""

from __future__ import annotations

from sqlmodel import col, select

from fastapi import APIRouter

from app.api.deps import CurrentSuperUser, SessionDep
from app.features.product.models.price_group import (
    PriceGroup,
    PriceGroupPublic,
    PriceGroupsPublic,
)

router = APIRouter(prefix="/admin/price-groups", tags=["admin-price-groups"])


@router.get("", response_model=PriceGroupsPublic)
async def list_price_groups(
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> PriceGroupsPublic:
    """List all active price groups (ordered by label)."""
    stmt = (
        select(PriceGroup)
        .where(col(PriceGroup.is_active).is_(True))
        .order_by(col(PriceGroup.label).asc())
    )
    result = await session.exec(stmt)
    groups = list(result.all())
    return PriceGroupsPublic(
        data=[PriceGroupPublic.model_validate(g) for g in groups],
        count=len(groups),
    )
