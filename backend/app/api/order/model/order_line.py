import uuid

from app.api.base.models import Base, BaseCreate, BaseUpdate, BasePublic
from app.api.order.model import Order
from sqlmodel import Field, Relationship, SQLModel


class OrderLineBase(Base):
    product_id: uuid.UUID = Field(
        foreign_key="product.id", description="ID of the product in the order line"
    )
    quantity: int = Field(
        description="Quantity of the product in the order line",
        ge=1,  # Ensure quantity is at least 1
    )
    description: str | None = Field(
        default=None,
        description="Description of the product in the order line"
    )


class OrderLineCreate(OrderLineBase, BaseCreate):
    pass


class OrderLineUpdate(OrderLineBase, BaseUpdate):
    product_id: uuid.UUID | None = None
    quantity: int | None = None
    description: str | None = None


class OrderLine(OrderLineBase, Base, table=True):
    __tablename__ = "order_line"
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    order_id: uuid.UUID = Field(
        foreign_key="order.id", description="ID of the order this line belongs to"
    )
    order: Order = Relationship(back_populates="order_lines")


class OrderLinePublic(OrderLineBase, BasePublic):
    id: uuid.UUID = Field(default_factory=uuid.uuid4, primary_key=True)
    order_id: uuid.UUID
    product_id: uuid.UUID
    quantity: int


class OrderLinesPublic(SQLModel):
    data: list[OrderLinePublic] = Field(default_factory=list)
    count: int = Field(default=0, description="Total number of order lines")
