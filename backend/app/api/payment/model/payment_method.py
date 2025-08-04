import uuid

from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic
from sqlmodel import Field, Relationship, SQLModel


class PaymentMethodBase(Base):
    name: str = Field(..., description="Name of the payment method")
    description: str = Field(None, description="Description of the payment method")
    # fee: float = Field(..., description="Fee associated with the payment method")
    # provider: str = Field(
    #     None, description="Payment provider associated with this method"
    # )


class PaymentMethodCreate(PaymentMethodBase, BaseCreate):
    pass


class PaymentMethodUpdate(PaymentMethodBase, BaseUpdate):
    pass


class PaymentMethod(PaymentMethodBase, BasePublic, table=True):
    __tablename__ = "payment_methods"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)
    payments: list["Payment"] = Relationship(back_populates="payment_methods")


class PaymentMethodPublic(PaymentMethodBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentMethodsPublic(SQLModel):
    data: list[PaymentMethodPublic] = Field(
        default_factory=list, description="List of payment methods"
    )
