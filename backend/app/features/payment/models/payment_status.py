import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class PaymentStatusBase(Base):
    """Represents payment status base."""

    name: str = Field(
        description="Name of the payment status (e.g., 'Pending', 'Completed', 'Failed')"
    )
    description: str | None = Field(
        default=None, description="Description of the payment status"
    )


class PaymentStatusCreate(PaymentStatusBase, BaseCreate):
    """Represents payment status create."""

    pass


class PaymentStatusUpdate(BaseUpdate):
    """Represents payment status update."""

    name: str | None = None
    description: str | None = None


class PaymentStatus(PaymentStatusBase, table=True):
    """Represents payment status."""

    __tablename__ = "payment_status"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentStatusPublic(PaymentStatusBase, BasePublic):
    """Represents payment status public."""

    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True, index=True)


class PaymentStatusesPublic(SQLModel):
    """Represents payment statuses public."""

    data: list[PaymentStatusPublic] = Field(
        default_factory=list, description="List of payment statuses"
    )
    count: int = Field(default=0, description="Total number of payment statuses")
