"""Admin endpoints: price groups.

Listing for the back-office screens that reference groups by id (payment
eligibility, group assignment), and a partial update for the settings a
group carries — today the deposit policy (« acompte à la commande »).
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter
from sqlmodel import col, select

from app.api.deps import CurrentSuperUser, SessionDep
from app.core.errors import AppError
from app.features.product.models.price_group import (
    PriceGroup,
    PriceGroupPublic,
    PriceGroupsPublic,
    PriceGroupUpdate,
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


@router.patch("/{group_id}", response_model=PriceGroupPublic)
async def update_price_group(
    group_id: uuid.UUID,
    body: PriceGroupUpdate,
    session: SessionDep,
    _current_user: CurrentSuperUser,
) -> PriceGroupPublic:
    """Partial update: discount on the reference price, fallback margin (default
    group), deposit policy (share, fee, imposed or offered)."""
    group = await session.get(PriceGroup, group_id)
    if group is None or not group.is_active:
        raise AppError(
            code="price_group.not_found",
            status_code=404,
            message="Groupe tarifaire introuvable",
            details={"group_id": str(group_id)},
        )
    changes = body.model_dump(exclude_unset=True)
    will_be_default = changes.get("default", group.default)
    discount = changes.get("discount_pct", group.discount_pct)
    if will_be_default and (discount or 0) > 0:
        # The default group's prices *are* the reference prices.
        raise AppError(
            code="price_group.default_discount",
            status_code=400,
            message=(
                "Le groupe par défaut donne les prix de référence : il ne peut pas "
                "avoir de remise"
            ),
            details={"group_id": str(group_id)},
        )
    for key, value in changes.items():
        setattr(group, key, value)
    session.add(group)
    await session.commit()
    await session.refresh(group)
    return PriceGroupPublic.model_validate(group)
