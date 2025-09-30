import uuid

from sqlmodel import Field, SQLModel, UniqueConstraint

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class InventoryBase(Base):
    quantity: int = Field(
        ge=0,
        description="Quantity available in the inventory",
    )
    product_id: uuid.UUID = Field(
        foreign_key="products.id",
        description="ID of the product associated with this inventory",
    )
    place_id: uuid.UUID | None = Field(
        default=None,
        foreign_key="places.id",
        description="ID of the place where the inventory is located",
    )
    compute_from_movements: bool = Field(
        default=True,
        description="Whether the inventory quantity is computed from movements",
    )


class InventoryCreate(InventoryBase, BaseCreate):
    pass


class InventoryUpdate(BaseUpdate):
    quantity: int | None = None
    compute_from_movements: bool | None = None


class Inventory(InventoryBase, Base, table=True):
    __tablename__ = "inventories"
    __table_args__ = {UniqueConstraint("product_id", "place_id")}
    id: uuid.UUID = Field(
        default_factory=uuid.uuid4,
        primary_key=True,
        index=True,
        description="Unique identifier for the inventory",
    )


class InventoryPublic(InventoryBase, BasePublic):
    id: uuid.UUID


class InventoriesPublic(SQLModel):
    inventories: list[InventoryPublic] = Field(
        default_factory=list,
        description="List of inventories",
    )
