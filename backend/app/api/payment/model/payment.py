import uuid

from sqlmodel import Enum, Field, Relationship, SQLModel
from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic
from app.api.model import PaymentMethod
from app.api.model import PaymentStatus


class PaymentBase(Base):
    amount: float = Field(..., gt=0, description="Amount to be paid")
    currency: str = Field(..., description="Currency of the payment")
    status: PaymentStatus = Field(..., description="Current status of the payment")


class PaymentCreate(PaymentBase, BaseCreate):
    pass


class PaymentUpdate(BaseUpdate, PaymentBase):
    amount: float | None = None
    currency: str | None = None
    status: PaymentStatus | None = None


class Payment(PaymentBase, Base, table=True):
    __tablename__ = "payments"
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment",
    )
    payment_method: PaymentMethod = Relationship(back_populates="payments")


class PaymentPublic(PaymentBase, BasePublic):
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        description="Unique identifier for the payment",
    )


class PaymentsPublic(SQLModel):
    data: list[PaymentPublic] = Field(
        default_factory=list, description="List of payments"
    )
