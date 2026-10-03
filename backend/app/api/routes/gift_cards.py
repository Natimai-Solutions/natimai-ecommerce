"""Gift cards and vouchers (R8 / confort — commerce).

The customer redeems a code into store credit from their account; the admin
issues cards and vouchers, lists them and cancels a lost one. Spending the
credit happens at checkout (``use_store_credit``), never here.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.api.deps import CurrentSuperUser, CurrentUser, SessionDep
from app.api.routes.store_credit import _balance_of
from app.core.rate_limit import rate_limited
from app.features.payment.models.gift_card import (
    GiftCardIssue,
    GiftCardPublic,
    GiftCardRedeem,
    GiftCardsPublic,
)
from app.features.payment.models.store_credit import StoreCreditBalance
from app.features.payment.services import gift_cards

router = APIRouter(tags=["gift-cards"])


@router.post(
    "/gift-cards/redeem",
    response_model=StoreCreditBalance,
    dependencies=[
        Depends(rate_limited("gift_card_redeem", limit=10, window_seconds=600))
    ],
)
async def redeem_gift_card(
    body: GiftCardRedeem, session: SessionDep, current_user: CurrentUser
) -> StoreCreditBalance:
    """Credit the card's amount to the customer's store credit."""
    user_id = current_user.id
    await gift_cards.redeem(session, code=body.code, user=current_user)
    await session.commit()
    return await _balance_of(session, user_id)


@router.get("/admin/gift-cards", response_model=GiftCardsPublic)
async def list_gift_cards(
    session: SessionDep,
    _admin: CurrentSuperUser,
    q: Annotated[str | None, Query(max_length=120)] = None,
    kind: Annotated[str | None, Query(max_length=20)] = None,
    state: Annotated[str | None, Query(max_length=20)] = None,
    skip: Annotated[int, Query(ge=0)] = 0,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> GiftCardsPublic:
    """Every card, newest first; filters on text, kind and computed state."""
    data, count = await gift_cards.list_cards(
        session, q=q, kind=kind, state=state, skip=skip, limit=limit
    )
    return GiftCardsPublic(data=data, count=count)


@router.post("/admin/gift-cards", response_model=list[GiftCardPublic])
async def issue_gift_cards(
    body: GiftCardIssue, session: SessionDep, admin: CurrentSuperUser
) -> list[GiftCardPublic]:
    """Issue ``count`` gift cards, or one nominative voucher."""
    cards = await gift_cards.issue(
        session,
        kind=body.kind,
        amount=body.amount,
        count=body.count,
        recipient_email=body.recipient_email,
        note=body.note,
        expires_at=body.expires_at or await gift_cards.default_expiry(session),
        created_by_id=admin.id,
    )
    await session.commit()
    for card in cards:
        await session.refresh(card)
    return [gift_cards.to_public(c) for c in cards]


@router.post("/admin/gift-cards/{card_id}/cancel", response_model=GiftCardPublic)
async def cancel_gift_card(
    card_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> GiftCardPublic:
    """Cancel a card that was not redeemed (lost, issued by mistake)."""
    card = await gift_cards.set_active(session, card_id=card_id, active=False)
    await session.commit()
    await session.refresh(card)
    return gift_cards.to_public(card)


@router.post("/admin/gift-cards/{card_id}/restore", response_model=GiftCardPublic)
async def restore_gift_card(
    card_id: uuid.UUID, session: SessionDep, _admin: CurrentSuperUser
) -> GiftCardPublic:
    """Undo a cancellation."""
    card = await gift_cards.set_active(session, card_id=card_id, active=True)
    await session.commit()
    await session.refresh(card)
    return gift_cards.to_public(card)
