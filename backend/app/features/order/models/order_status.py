import uuid

from sqlmodel import Field, SQLModel
from app.features.base.models import Base, BaseCreate, BaseUpdate, BasePublic


class OrderStatusBase(SQLModel):
    name: str = Field(description="Nom du statut (ex: 'En attente', 'Expédiée')")


class OrderStatusCreate(OrderStatusBase, BaseCreate):
    pass


class OrderStatusUpdate(BaseUpdate):
    name: str | None = None


class OrderStatus(OrderStatusBase, Base, table=True):
    __tablename__ = "order_statuses"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)


class OrderStatusPublic(OrderStatusBase, BasePublic):
    id: uuid.UUID


class OrderStatusesPublic(SQLModel):
    data: list[OrderStatusPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Nombre total de statuts")
