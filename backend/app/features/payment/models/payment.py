import uuid

from sqlmodel import Enum, Field, Relationship, SQLModel
from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class PaymentBase(Base):
    amount: float = Field(..., gt=0, description="Amount to be paid")
    currency: str = Field(..., description="Currency of the payment")


class PaymentCreate(PaymentBase, BaseCreate):
    pass


class PaymentUpdate(BaseUpdate, PaymentBase):
    amount: float | None = None
    currency: str | None = None


class Payment(PaymentBase, Base, table=True):
    __tablename__ = "payments"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment",
    )
    payment_method_id: uuid.UUID = Field(
        foreign_key="payment_methods.id",
        description="ID of the payment method used"
    )
    payment_status_id: uuid.UUID = Field(
        foreign_key="payment_status.id",
        description="ID of the payment status"
    )


class PaymentPublic(PaymentBase, BasePublic):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment",
    )
    payment_method_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="payment_methods.id",
        description="ID of the payment method used"
    )
    payment_status_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="payment_status.id",
        description="ID of the payment status"
    )


class PaymentsPublic(SQLModel):
    data: list[PaymentPublic] = Field(
        default_factory=list, description="List of payments"
    )
