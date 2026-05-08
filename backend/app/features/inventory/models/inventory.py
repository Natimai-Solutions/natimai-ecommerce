import uuid
from decimal import Decimal

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class InventoryBase(Base):
    quantity: Decimal = Field(
        default=Decimal("0.00"),
        ge=0,
        max_digits=10,
        decimal_places=2,
        description="Quantity available in the inventory",
    )
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        index=True,
        description="ID of the product associated with this inventory",
    )
    place_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="places.id",
        index=True,
        description="ID of the place where the inventory is located",
    )
    compute_from_movements: bool = Field(
        default=True,
        description="Whether the inventory quantity is computed from movements",
    )


class InventoryCreate(InventoryBase, BaseCreate):
    pass


class InventoryUpdate(BaseUpdate):
    quantity: Decimal | None = None
    product_id: uuid.UUID | None = None
    place_id: uuid.UUID | None = None
    compute_from_movements: bool | None = None


class Inventory(InventoryBase, table=True):
    __tablename__ = "inventories"
    __table_args__ = (UniqueConstraint("product_id", "place_id"),)
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the inventory",
    )


class InventoryPublic(InventoryBase, BasePublic):
    id: uuid.UUID


class InventoriesPublic(SQLModel):
    data: list[InventoryPublic] = Field(
        default_factory=list,
        description="List of inventories",
    )
    count: int = Field(
        default=0,
        description="Total number of inventories",
    )
