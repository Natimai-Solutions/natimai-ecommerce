# mypy: disable-error-code="assignment,misc,override"

import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentMethodBase(Base):
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


class PaymentMethodCreate(PaymentMethodBase, BaseCreate):
    pass


class PaymentMethodUpdate(PaymentMethodBase, BaseUpdate):
    name: str | None = None


class PaymentMethod(PaymentMethodBase, table=True):
    __tablename__ = "payment_methods"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentMethodPublic(PaymentMethodBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentMethodsPublic(SQLModel):
    data: list[PaymentMethodPublic] = Field(
        default_factory=list, description="List of payment methods"
    )
    count: int = Field(default=0, description="Total number of payment methods")
