# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentBase(Base):
    amount: Decimal = Field(
        ...,
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Amount to be paid expressed in the payment currency",
    )
    currency: str = Field(
        default="XPF", description="Currency of the payment (XPF, EUR, etc.)"
    )


class PaymentCreate(PaymentBase, BaseCreate):
    order_id: uuid.UUID | None = Field(
        default=None, description="ID of the order associated with this payment"
    )
    user_id: uuid.UUID = Field(description="ID of the user making the payment")


class PaymentUpdate(PaymentBase, BaseUpdate):
    amount: Decimal | None = None
    currency: str | None = None
    order_id: uuid.UUID | None = None
    user_id: uuid.UUID | None = None


class Payment(PaymentBase, table=True):
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
    payzen_trans_id: str | None = Field(
        default=None, index=True, description="Payzen transaction UUID"
    )
    payzen_order_id: str | None = Field(
        default=None, index=True, description="Payzen order ID (same as payment id)"
    )
    payzen_payment_method: str | None = Field(
        default=None, description="Payment method used (CB, Visa, Mastercard)"
    )
    payzen_status: str | None = Field(
        default=None, description="Payzen transaction status (PAID, REFUSED, etc.)"
    )
    payzen_error_code: str | None = Field(
        default=None, description="Payzen error code if any"
    )
    payzen_form_token: str | None = Field(
        default=None, description="Payzen form token generated for this payment"
    )
    payzen_data: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Raw Payzen response data",
    )


class PaymentPublic(PaymentBase, BasePublic):
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
    payzen_trans_id: str | None = None
    payzen_order_id: str | None = None
    payzen_payment_method: str | None = None
    payzen_status: str | None = None


class PaymentsPublic(SQLModel):
    data: list[PaymentPublic] = Field(
        default_factory=list, description="List of payments"
    )
    count: int = Field(default=0, description="Total number of payments")
