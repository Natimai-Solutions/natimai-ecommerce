"""Store credit (« avoir-crédit ») : the customer's balance and ledger, and
the admin grants / revocations.

Spending the credit happens at checkout (``use_store_credit``), never here.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter

from app.api.deps import CurrentSuperUser, CurrentUser, SessionDep
from app.core.config import settings
from app.core.errors import AppError
from app.features.payment.models.store_credit import (
    StoreCreditBalance,
    StoreCreditEntryPublic,
    StoreCreditGrant,
)
from app.features.payment.services import store_credit
from app.features.user.models.user import User

router = APIRouter(tags=["store-credit"])


async def _balance_of(session: SessionDep, user_id: uuid.UUID) -> StoreCreditBalance:
    return StoreCreditBalance(
        user_id=user_id,
        currency=settings.REFERENCE_CURRENCY,
        balance=await store_credit.balance(session, user_id),
        entries=[
            StoreCreditEntryPublic.model_validate(e)
            for e in await store_credit.entries(session, user_id)
        ],
    )


@router.get("/store-credit/me", response_model=StoreCreditBalance)
async def my_store_credit(
    session: SessionDep, current_user: CurrentUser
) -> StoreCreditBalance:
    """The customer's credit balance and its history."""
    return await _balance_of(session, current_user.id)


@router.get("/admin/users/{user_id}/store-credit", response_model=StoreCreditBalance)
async def user_store_credit(
    user_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> StoreCreditBalance:
    """A customer's credit balance and ledger."""
    return await _balance_of(session, user_id)


@router.post("/admin/users/{user_id}/store-credit", response_model=StoreCreditBalance)
async def grant_store_credit(
    user_id: uuid.UUID,
    body: StoreCreditGrant,
    session: SessionDep,
    admin: CurrentSuperUser,
) -> StoreCreditBalance:
    """Grant credit (positive amount) or take it back (negative), with a
    reason; optionally tied to the order it compensates."""
    if await session.get(User, user_id) is None:
        raise AppError(
            code="user.not_found",
            status_code=404,
            message="Client introuvable",
            details={"user_id": str(user_id)},
        )
    await store_credit.grant(
        session,
        user_id=user_id,
        amount=body.amount,
        reason=body.reason,
        currency=settings.REFERENCE_CURRENCY,
        order_id=body.order_id,
        admin=admin,
    )
    await session.commit()
    return await _balance_of(session, user_id)
