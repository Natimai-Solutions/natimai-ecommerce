# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.core.config import reference_currency
from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentBase(Base):
    """Represents payment base."""

    amount: Decimal = Field(
        ...,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Amount to be paid expressed in the payment currency",
    )
    currency: str = Field(
        default_factory=reference_currency,
        description="Currency of the payment (XPF, EUR, etc.)",
    )
    provider_code: str = Field(
        default="payzen",
        max_length=50,
        index=True,
        description="Payment provider identifier (payzen, stripe, manual_check, etc.)",
    )


class PaymentCreate(PaymentBase, BaseCreate):
    """Represents payment create."""

    order_id: uuid.UUID | None = Field(
        default=None, description="ID of the order associated with this payment"
    )
    user_id: uuid.UUID = Field(description="ID of the user making the payment")


class PaymentUpdate(PaymentBase, BaseUpdate):
    """Represents payment update."""

    amount: Decimal | None = None
    currency: str | None = None
    provider_code: str | None = None
    order_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None
    provider_reference: str | None = None
    provider_data: dict[str, Any] | None = None


class Payment(PaymentBase, table=True):
    """Represents payment."""

    __tablename__ = "payments"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the payment",
    )
    order_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="orders.id",
        nullable=True,
        index=True,
        description="ID of the order associated with this payment",
    )
    user_id: uuid.UUID = Field(
        foreign_key="users.id",
        nullable=False,
        index=True,
        description="ID of the user making the payment",
    )
    payment_method_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="payment_methods.id",
        nullable=True,
        index=True,
        description="ID of the payment method used",
    )
    payment_status_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="payment_status.id",
        nullable=True,
        index=True,
        description="ID of the payment status",
    )
    provider_reference: str | None = Field(
        default=None,
        max_length=255,
        index=True,
        description="Provider-side payment reference (transaction id, external order id, etc.)",
    )
    provider_data: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Raw provider payload for provider-agnostic workflows",
    )
    kind: str = Field(
        default="full",
        max_length=20,
        description="full | deposit | balance — which part of the order it settles",
    )


class PaymentPublic(PaymentBase, BasePublic):
    """Represents payment public."""

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment",
    )
    order_id: uuid.UUID | None = Field(
        default=None,
        description="ID of the order associated with this payment",
    )
    user_id: uuid.UUID = Field(description="ID of the user making the payment")
    payment_method_id: uuid.UUID | None = Field(
        default=None,
        description="ID of the payment method used",
    )
    payment_status_id: uuid.UUID | None = Field(
        default=None,
        description="ID of the payment status",
    )
    provider_reference: str | None = None
    provider_data: dict[str, Any] | None = None


class PaymentsPublic(SQLModel):
    """Represents payments public."""

    data: list[PaymentPublic] = Field(
        default_factory=list, description="List of payments"
    )
    count: int = Field(default=0, description="Total number of payments")
