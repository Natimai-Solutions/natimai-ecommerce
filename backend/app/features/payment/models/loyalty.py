"""Loyalty points (R8 / confort — commerce): a ledger per customer.

Points are earned when an order is fully paid (one point per
``loyalty_amount_per_point`` of the order's goods, gift cards excluded),
taken back proportionally when the order is refunded, and converted by the
customer into store credit (``loyalty_point_value`` each) from their account.
Like the store credit, the balance is the sum of signed entries: auditable,
never out of sync.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from pydantic import field_validator
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BasePublic

LOYALTY_KINDS: tuple[str, ...] = ("earn", "convert", "revoke", "adjust")


class LoyaltyEntryBase(Base):
    """A signed movement of points."""

    user_id: uuid.UUID = Field(foreign_key="users.id", index=True)
    points: int = Field(description="Signé : positif gagné, négatif converti ou repris")
    kind: str = Field(max_length=20, description="earn | convert | revoke | adjust")
    reason: str | None = Field(default=None, max_length=500)
    order_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="orders.id",
        index=True,
        description="Commande à l'origine des points (gain ou reprise)",
    )
    store_credit_entry_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="store_credit_entries.id",
        description="Avoir créé par une conversion",
    )

    @field_validator("kind")
    @classmethod
    def _known_kind(cls, value: str) -> str:
        if value not in LOYALTY_KINDS:
            raise ValueError(f"type inconnu '{value}'")
        return value


class LoyaltyEntry(LoyaltyEntryBase, table=True):
    """Represents one loyalty ledger entry."""

    __tablename__ = "loyalty_entries"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class LoyaltyEntryPublic(LoyaltyEntryBase, BasePublic):
    """Ledger entry as the customer and the admin see it."""

    id: uuid.UUID


class LoyaltyRules(SQLModel):
    """How the programme works, for the storefront wording."""

    enabled: bool
    currency: str
    amount_per_point: Decimal = Field(description="Montant d'achat qui vaut 1 point")
    point_value: Decimal = Field(description="Valeur d'un point converti en avoir")
    min_points_to_convert: int


class LoyaltyAccount(SQLModel):
    """Balance, ledger and rules of one customer."""

    user_id: uuid.UUID
    points: int
    credit_value: Decimal = Field(description="Valeur en avoir du solde de points")
    rules: LoyaltyRules
    entries: list[LoyaltyEntryPublic] = Field(default_factory=list)


class LoyaltyConvert(SQLModel):
    """Customer payload: how many points to turn into store credit."""

    points: int = Field(ge=1)


class LoyaltyAdjust(SQLModel):
    """Admin payload: add (positive) or take back (negative) points."""

    points: int
    reason: str = Field(min_length=1, max_length=500)
    order_id: uuid.UUID | None = None

    @field_validator("points")
    @classmethod
    def _non_zero(cls, value: int) -> int:
        if value == 0:
            raise ValueError("le nombre de points doit être différent de zéro")
        return value
