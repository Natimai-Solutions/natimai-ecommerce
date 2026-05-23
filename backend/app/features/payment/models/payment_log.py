# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal
from typing import Any

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentLogBase(Base):
    """Represents payment log base."""

    payment_id: uuid.UUID = Field(
        foreign_key="payments.id",
        nullable=False,
        index=True,
        description="ID of the payment associated with this log",
    )
    provider_reference: str | None = Field(
        default=None,
        index=True,
        description="Provider-side transaction reference",
    )
    provider_order_reference: str | None = Field(
        default=None,
        index=True,
        description="Provider-side order/payment reference",
    )
    amount: Decimal = Field(
        ...,
        max_digits=12,
        decimal_places=2,
        description="Amount expressed in the payment currency",
    )
    payment_method: str | None = Field(
        default=None, description="Payment method used (CB, Visa, Mastercard, etc.)"
    )
    status: str | None = Field(
        default=None, description="Payzen transaction status (PAID, REFUSED, etc.)"
    )
    error_code: str | None = Field(default=None, description="Payzen error code if any")
    raw_data: dict[str, Any] | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Raw Payzen IPN data",
    )


class PaymentLogCreate(PaymentLogBase, BaseCreate):
    """Represents payment log create."""

    pass


class PaymentLogUpdate(PaymentLogBase, BaseUpdate):
    """Represents payment log update."""

    payment_id: uuid.UUID | None = None
    provider_reference: str | None = None
    provider_order_reference: str | None = None
    amount: Decimal | None = None
    payment_method: str | None = None
    status: str | None = None
    error_code: str | None = None
    raw_data: dict[str, Any] | None = None


class PaymentLog(PaymentLogBase, table=True):
    """Represents payment log."""

    __tablename__ = "payment_logs"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the payment log",
    )


class PaymentLogPublic(PaymentLogBase, BasePublic):
    """Represents payment log public."""

    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment log",
    )


class PaymentLogsPublic(SQLModel):
    """Represents payment logs public."""

    data: list[PaymentLogPublic] = Field(
        default_factory=list, description="List of payment logs"
    )
    count: int = Field(default=0, description="Total number of payment logs")
