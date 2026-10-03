"""Loyalty points (R8 / confort — commerce): the customer's balance and the
conversion into store credit; the admin's view and adjustments."""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentSuperUser, CurrentUser, SessionDep
from app.core.errors import AppError
from app.features.payment.models.loyalty import (
    LoyaltyAccount,
    LoyaltyAdjust,
    LoyaltyConvert,
)
from app.features.payment.services import loyalty
from app.features.user.models.user import User

router = APIRouter(tags=["loyalty"])


@router.get("/loyalty/me", response_model=LoyaltyAccount)
async def my_loyalty(session: SessionDep, current_user: CurrentUser) -> LoyaltyAccount:
    """Points, their value in store credit, the ledger and the rules."""
    return await loyalty.account(session, current_user.id)


@router.post("/loyalty/convert", response_model=LoyaltyAccount)
async def convert_points(
    body: LoyaltyConvert, session: SessionDep, current_user: CurrentUser
) -> LoyaltyAccount:
    """Turn points into store credit, spent at checkout like any avoir."""
    user_id = current_user.id
    await loyalty.convert(session, user_id=user_id, points=body.points)
    await session.commit()
    return await loyalty.account(session, user_id)


@router.get("/admin/users/{user_id}/loyalty", response_model=LoyaltyAccount)
async def user_loyalty(
    user_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> LoyaltyAccount:
    """A customer's points and ledger."""
    return await loyalty.account(session, user_id)


@router.post("/admin/users/{user_id}/loyalty", response_model=LoyaltyAccount)
async def adjust_loyalty(
    user_id: uuid.UUID,
    body: LoyaltyAdjust,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> LoyaltyAccount:
    """Add or take back points, with a reason."""
    if await session.get(User, user_id) is None:
        raise AppError(
            code="user.not_found",
            status_code=404,
            message="Client introuvable",
            details={"user_id": str(user_id)},
        )
    await loyalty.adjust(
        session,
        user_id=user_id,
        points=body.points,
        reason=body.reason,
        order_id=body.order_id,
        admin=admin,
    )
    await session.commit()
    return await loyalty.account(session, user_id)
