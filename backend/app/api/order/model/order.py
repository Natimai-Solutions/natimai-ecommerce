import uuid
from sqlmodel import Field, Relationship, SQLModel

from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic
from app.api.order.model import OrderStatus, OrderLine


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
    __tablename__ = "order"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    status_id: uuid.UUID = Field(
        foreign_key="order_status.id", description="ID of the order status"
    )
    status: OrderStatus = Relationship(back_populates="orders")
    order_lines: list[OrderLine] = Relationship(back_populates="order")


class OrderPublic(OrderBase, BasePublic):
    id: uuid.UUID


class OrdersPublic(SQLModel):
    data: list[OrderPublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of orders")
