import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class OrderBase(Base):
    name: str = Field(description="Name of the Order")
    description: str | None = Field(
        default=None,
        description="Description of the Order ( e.g product )",
        max_length=255,
    )


class OrderCreate(OrderBase, BaseCreate):
    pass


class OrderUpdate(OrderBase, BaseUpdate):
    name: str | None = None
    description: str | None = None


class Order(OrderBase, Base, table=True):
    __tablename__ = "orders"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    order_status_id: uuid.UUID = Field(
        foreign_key="order_statuses.id", description="ID of the order status"
    )


class OrderPublic(OrderBase, BasePublic):
    id: uuid.UUID
    order_status_id: uuid.UUID


class OrdersPublic(SQLModel):
    data: list[OrderPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of orders")
