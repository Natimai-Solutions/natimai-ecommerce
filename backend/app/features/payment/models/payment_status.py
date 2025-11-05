import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentStatusBase(Base):
    name: str = Field(
        description="Name of the payment status (e.g., 'Pending', 'Completed', 'Failed')"
    )
    description: str | None = Field(
        default=None, description="Description of the payment status"
    )


class PaymentStatusCreate(PaymentStatusBase, BaseCreate):
    pass


class PaymentStatusUpdate(BaseUpdate):
    name: str | None = None
    description: str | None = None


class PaymentStatus(PaymentStatusBase, table=True):
    __tablename__ = "payment_status"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentStatusPublic(PaymentStatusBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentStatusesPublic(SQLModel):
    data: list[PaymentStatusPublic] = Field(
        default_factory=list, description="List of payment statuses"
    )
    count: int = Field(default=0, description="Total number of payment statuses")
