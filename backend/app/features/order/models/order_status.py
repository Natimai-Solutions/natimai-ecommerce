import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class OrderStatusBase(Base):
    """Represents order status base."""

    name: str = Field(
        description="Nom du statut (ex: 'En attente', 'Expédiée')",
        max_length=100,
    )


class OrderStatusCreate(OrderStatusBase, BaseCreate):
    """Represents order status create."""

    pass


class OrderStatusUpdate(BaseUpdate):
    """Represents order status update."""

    name: str | None = None


class OrderStatus(OrderStatusBase, table=True):
    """Represents order status."""

    __tablename__ = "order_statuses"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class OrderStatusPublic(OrderStatusBase, BasePublic):
    """Represents order status public."""

    id: uuid.UUID


class OrderStatusesPublic(SQLModel):
    """Represents order statuses public."""

    data: list[OrderStatusPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Nombre total de statuts")
