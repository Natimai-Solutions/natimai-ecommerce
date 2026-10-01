# mypy: disable-error-code="assignment,misc,override"
"""Amounts actually received against a manual payment (R3-P2).

A manual payment (cash at the office, cheque, transfer) is the customer's
intent to pay a part of the order. Each amount the shop receives against it —
several cash instalments, a cheque cashed later — is a receipt. The payment is
settled (``Completed``, then ``payment.captured``) when its receipts add up to
its amount; until then the order is « partiellement payée ».

A cancelled receipt (bounced cheque, cash handed back) stays in the table with
``is_active=False`` and its reason: the history is never rewritten.
"""

import uuid
from datetime import datetime
from decimal import Decimal

from sqlalchemy import Column, DateTime
from sqlmodel import Field, SQLModel

from app.core.config import reference_currency
from app.features.base.models import Base

RECEIPT_METHODS: tuple[str, ...] = ("cash", "check", "transfer", "card", "other")


class PaymentReceipt(Base, table=True):
    """One amount received against a manual payment."""

    __tablename__ = "payment_receipts"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    payment_id: uuid.UUID = Field(foreign_key="payments.id", index=True)
    order_id: uuid.UUID | None = Field(
        default=None, foreign_key="orders.id", index=True, nullable=True
    )
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    currency: str = Field(default_factory=reference_currency, max_length=10)
    received_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    method: str = Field(max_length=20, description=" | ".join(RECEIPT_METHODS))
    reference: str | None = Field(
        default=None, max_length=100, description="Cheque number, transfer reference…"
    )
    note: str | None = Field(default=None, max_length=500)
    recorded_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    cancelled_at: datetime | None = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    cancelled_by_id: uuid.UUID | None = Field(
        default=None, foreign_key="users.id", nullable=True
    )
    cancel_reason: str | None = Field(default=None, max_length=500)


class PaymentReceiptPublic(SQLModel):
    """A receipt as the admin sees it."""

    id: uuid.UUID
    payment_id: uuid.UUID
    order_id: uuid.UUID | None
    amount: Decimal
    currency: str
    received_at: datetime
    method: str
    reference: str | None
    note: str | None
    recorded_by_id: uuid.UUID | None
    is_active: bool
    cancelled_at: datetime | None
    cancel_reason: str | None
