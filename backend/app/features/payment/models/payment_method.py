# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal

from sqlmodel import JSON, Column, Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentMethodBase(Base):
    """Represents payment method base."""

    name: str = Field(description="Name of the payment method")
    description: str | None = Field(
        default=None,
        description="Description of the payment method",
        max_length=255,
    )
    fee: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Fee associated with the payment method",
    )
    provider_code: str = Field(
        default="payzen",
        max_length=50,
        index=True,
        description="Provider identifier used by payment dispatch",
    )
    requires_admin_validation: bool = Field(
        default=False,
        description="Whether this method requires explicit admin validation",
    )
    requires_document_upload: bool = Field(
        default=False,
        description="Whether this method requires a supporting document upload",
    )
    sort_order: int = Field(
        default=0,
        description="Display order in checkout payment method listing",
    )
    max_amount: Decimal | None = Field(
        default=None,
        ge=0,
        max_digits=12,
        decimal_places=2,
        description="Maximum transaction amount (NULL = no limit)",
    )
    deposit_allowed: bool = Field(
        default=True,
        description=(
            "Whether this method can pay the deposit of a deposit order "
            "(the balance can always be paid by any eligible method)"
        ),
    )
    instructions: str | None = Field(
        default=None,
        max_length=2000,
        description=(
            "Instructions shown and e-mailed to the customer for this method "
            "(IBAN, office address…). NULL = the instructions of its type"
        ),
    )
    currencies: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False, server_default="[]"),
        description=(
            "ISO codes of the currencies this method can collect in. Empty = "
            "any (the order is charged in the shop's reference currency). A "
            "customer whose display currency is not listed is warned at "
            "checkout that the payment is made in another currency, with "
            "the converted amount."
        ),
    )


class PaymentMethodCreate(PaymentMethodBase, BaseCreate):
    """Represents payment method create."""

    pass


class PaymentMethodUpdate(PaymentMethodBase, BaseUpdate):
    """Represents payment method update."""

    name: str | None = None
    description: str | None = None
    fee: Decimal | None = None
    provider_code: str | None = None
    requires_admin_validation: bool | None = None
    requires_document_upload: bool | None = None
    sort_order: int | None = None
    max_amount: Decimal | None = None
    deposit_allowed: bool | None = None
    instructions: str | None = None
    currencies: list[str] | None = None


class PaymentMethod(PaymentMethodBase, table=True):
    """Represents payment method."""

    __tablename__ = "payment_methods"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentMethodPublic(PaymentMethodBase, BasePublic):
    """Represents payment method public."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentMethodsPublic(SQLModel):
    """Represents payment methods public."""

    data: list[PaymentMethodPublic] = Field(
        default_factory=list, description="List of payment methods"
    )
    count: int = Field(default=0, description="Total number of payment methods")
