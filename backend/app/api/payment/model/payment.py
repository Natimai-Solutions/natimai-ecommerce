import uuid
import datetime

from sqlmodel import Field, Relationship, SQLModel
from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class PaymentBase(Base):
    amount: float = Field(..., description="Amount to be paid")
    currency: str = Field(..., description="Currency of the payment")
    status: str = Field(..., description="Current status of the payment")
    transaction_id: str = Field(None, description="Transaction ID for the payment")


class PaymentCreate(PaymentBase, BaseCreate):
    pass


class PaymentUpdate(BaseUpdate, PaymentBase):
    pass


class Payment(PaymentBase, Base, table=True):
    __tablename__ = "payments"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment",
    )
    is_active: bool = Field(
        default=True, description="Indicates if the payment is active"
    )
    payment_method: "PaymentMethod" = Relationship(back_populates="payments")


class PaymentPublic(PaymentBase, BasePublic):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment",
    )
    is_active: bool = Field(
        default=True, description="Indicates if the payment is active"
    )


class PaymentsPublic(SQLModel):
    data: list[PaymentPublic] = Field(
        default_factory=list, description="List of payments"
    )
