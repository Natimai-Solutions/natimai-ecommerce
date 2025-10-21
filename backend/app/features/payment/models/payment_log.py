import uuid

from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentLogBase(SQLModel):
    payment_id: uuid.UUID = Field(
        foreign_key="payments.id", 
        nullable=False, 
        index=True, 
        description="ID of the payment associated with this log"
    )
    payzen_trans_id: str | None = Field(
        default=None, index=True, description="Payzen transaction UUID"
    )
    payzen_order_id: str | None = Field(
        default=None, index=True, description="Payzen order ID"
    )
    amount: int = Field(..., description="Amount in cents/smallest currency unit")
    payment_method: str | None = Field(
        default=None, description="Payment method used (CB, Visa, Mastercard, etc.)"
    )
    status: str | None = Field(
        default=None, description="Payzen transaction status (PAID, REFUSED, etc.)"
    )
    error_code: str | None = Field(
        default=None, description="Payzen error code if any"
    )
    raw_data: dict | None = Field(
        default=None,
        sa_column=Column(JSON),
        description="Raw Payzen IPN data",
    )


class PaymentLogCreate(PaymentLogBase, BaseCreate):
    pass


class PaymentLogUpdate(PaymentLogBase, BaseUpdate):
    payment_id: uuid.UUID | None = None
    payzen_trans_id: str | None = None
    payzen_order_id: str | None = None
    amount: int | None = None
    payment_method: str | None = None
    status: str | None = None
    error_code: str | None = None
    raw_data: dict | None = None


class PaymentLog(PaymentLogBase, Base, table=True):
    __tablename__ = "payment_logs"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the payment log",
    )


class PaymentLogPublic(PaymentLogBase, BasePublic):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment log",
    )


class PaymentLogsPublic(SQLModel):
    data: list[PaymentLogPublic] = Field(
        default_factory=list, description="List of payment logs"
    )
    count: int = Field(default=0, description="Total number of payment logs")
