# mypy: disable-error-code="assignment,misc,override"

import uuid
from datetime import datetime
from decimal import Decimal

from sqlmodel import Field

from app.core.config import reference_currency
from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class RefundBase(Base):
    """A refund (full or partial) applied to a captured payment."""

    payment_id: uuid.UUID = Field(
        foreign_key="payments.id",
        index=True,
        description="The payment being refunded",
    )
    order_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="orders.id",
        index=True,
        description="Order linked to the refunded payment, if any",
    )
    amount: Decimal = Field(
        gt=0,
        max_digits=12,
        decimal_places=2,
        description="Refunded amount, expressed in the payment currency",
    )
    currency: str = Field(default_factory=reference_currency, max_length=50)
    reason: str | None = Field(default=None, max_length=1024)
    status: str = Field(
        default="pending",
        max_length=50,
        index=True,
        description="completed | pending | failed",
    )
    provider_reference: str | None = Field(
        default=None,
        max_length=255,
        description="External refund reference (provider transaction id)",
    )
    processed_at: datetime | None = Field(
        default=None, description="When the refund became effective (completed)"
    )


class Refund(RefundBase, table=True):
    """Refund record."""

    __tablename__ = "refunds"

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class RefundCreate(RefundBase, BaseCreate):
    """Represents refund create."""

    pass


class RefundUpdate(BaseUpdate):
    """Represents refund update."""

    status: str | None = None
    provider_reference: str | None = None
    processed_at: datetime | None = None


class RefundPublic(RefundBase, BasePublic):
    """Represents refund public."""

    id: uuid.UUID
