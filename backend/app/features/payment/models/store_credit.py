"""Store credit (« avoir-crédit ») : a balance the customer spends on a
next order, as opposed to the accounting credit note (``CreditNote``) that
documents a refund.

A ledger, not a balance column: every grant (goodwill, refund kept as
credit, backorder compensation), use and revocation is a signed entry, and
the balance is their sum. Auditable, and never out of sync.
"""

import uuid
from decimal import Decimal

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BasePublic

STORE_CREDIT_KINDS: tuple[str, ...] = ("grant", "use", "revoke")


class StoreCreditEntryBase(Base):
    """Represents store credit entry base."""

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    amount: Decimal = Field(
        max_digits=12,
        decimal_places=2,
        description="Signé : positif pour un octroi, négatif pour une utilisation",
    )
    currency: str = Field(default="XPF", max_length=8)
    kind: str = Field(max_length=20, description="grant | use | revoke")
    reason: str | None = Field(default=None, max_length=500)
    order_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="orders.id",
        index=True,
        description="Commande d'origine (octroi) ou réglée (utilisation)",
    )
    payment_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="payments.id",
        description="Paiement « store_credit » créé par une utilisation",
    )

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in STORE_CREDIT_KINDS:
            raise ValueError(f"type inconnu '{value}'")
        return value


class StoreCreditEntry(StoreCreditEntryBase, table=True):
    """Represents store credit entry."""

    __tablename__ = "store_credit_entries"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class StoreCreditEntryPublic(StoreCreditEntryBase, BasePublic):
    """Represents store credit entry public."""

    id: uuid.UUID


class StoreCreditGrant(SQLModel):
    """Admin payload: grant (positive) or revoke (negative) credit."""

    amount: Decimal = Field(max_digits=12, decimal_places=2)
    reason: str = Field(min_length=1, max_length=500)
    order_id: uuid.UUID | None = None


class StoreCreditBalance(SQLModel):
    """Balance and ledger of one customer."""

    user_id: uuid.UUID
    currency: str
    balance: Decimal
    entries: list[StoreCreditEntryPublic] = Field(default_factory=list)
