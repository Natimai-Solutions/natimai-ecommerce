"""Gift cards and vouchers (« cartes cadeaux » et « bons d'achat », R8 / confort).

Both are a prepaid code worth a fixed amount, turned into store credit
(:mod:`app.features.payment.models.store_credit`) when its holder redeems it
from their account: the credit is then spent at checkout like any avoir, in
one or several orders. The difference is who may redeem:

* a **gift card** is a bearer code — bought in the shop (a product carrying
  ``gift_card_amount``) or issued by the admin — anyone with the code uses it;
* a **voucher** is nominative: issued by the admin for one customer's e-mail
  address, only that account may redeem it (a commercial gesture, a prize…).

A code is redeemed in one go, for its full amount; partial use happens on the
store-credit side.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.core.config import reference_currency
from app.features.base.models import Base, BasePublic

GIFT_CARD_KINDS: tuple[str, ...] = ("gift_card", "voucher")
KIND_GIFT_CARD = "gift_card"
KIND_VOUCHER = "voucher"

#: ``XXXX-XXXX-XXXX-XXXX`` once formatted.
CODE_LENGTH = 16


class GiftCardBase(Base):
    """Fields shared by the table and its public views."""

    kind: str = Field(max_length=20, description="gift_card | voucher")
    amount: Decimal = Field(max_digits=12, decimal_places=2, gt=0)
    currency: str = Field(default_factory=reference_currency, max_length=8)
    recipient_email: str | None = Field(
        default=None,
        max_length=255,
        description=(
            "Voucher: the only account allowed to redeem. Gift card bought in "
            "the shop: the buyer, for information."
        ),
    )
    note: str | None = Field(
        default=None, max_length=500, description="Admin note (occasion, reason)"
    )
    expires_at: datetime | None = Field(default=None, description="None: never")
    order_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="orders.id",
        index=True,
        description="Order the card was bought in (None when issued by the admin)",
    )

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in GIFT_CARD_KINDS:
            raise ValueError(f"type inconnu '{value}'")
        return value


class GiftCard(GiftCardBase, table=True):
    """A prepaid code and what became of it."""

    __tablename__ = "gift_cards"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    code: str = Field(max_length=32, unique=True, index=True)
    # ``is_active`` (from Base) False = cancelled by the admin; ``created_by_id``
    # = the admin who issued it (None for a card bought in the shop).
    redeemed_at: datetime | None = Field(default=None)
    redeemed_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", index=True
    )
    store_credit_entry_id: uuid.UUID | None = Field(
        default=None, foreign_key="store_credit_entries.id"
    )


class GiftCardPublic(GiftCardBase, BasePublic):
    """Admin view of a card: the full code is shown to the admin only."""

    id: uuid.UUID
    code: str
    redeemed_at: datetime | None = None
    redeemed_by_id: uuid.UUID | None = None
    redeemed_by_email: str | None = None
    state: str = Field(description="active | redeemed | expired | cancelled (computed)")


class GiftCardsPublic(SQLModel):
    """A page of cards."""

    data: list[GiftCardPublic]
    count: int


class GiftCardIssue(SQLModel):
    """Admin payload: issue ``count`` cards or one nominative voucher."""

    kind: str = Field(default=KIND_GIFT_CARD, max_length=20)
    amount: Decimal = Field(max_digits=12, decimal_places=2, gt=0)
    count: int = Field(default=1, ge=1, le=100)
    recipient_email: str | None = Field(default=None, max_length=255)
    note: str | None = Field(default=None, max_length=500)
    expires_at: datetime | None = None

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in GIFT_CARD_KINDS:
            raise ValueError(f"type inconnu '{value}'")
        return value


class GiftCardRedeem(SQLModel):
    """Customer payload: the code as typed (case and dashes do not matter)."""

    code: str = Field(min_length=4, max_length=64)
