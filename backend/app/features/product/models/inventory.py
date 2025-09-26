import uuid

from sqlmodel import Field, SQLModel

from app.features.base.models import Base, BaseCreate, BasePublic, BaseUpdate


class InventoryBase(Base):
    name: str = Field(
        description="Name of the inventory",
        max_length=100,
    )
    description: str | None = Field(
        default=None,
        max_length=500,
        description="Description of the inventory",
    )
    stock: int = Field(
        ge=0,
        description="Stock quantity available in the inventory",
    )


class InventoryCreate(InventoryBase, BaseCreate):
    pass


class InventoryUpdate(InventoryBase, BaseUpdate):
    description: str | None = None
    stock: int | None = None


class Inventory(InventoryBase, Base, table=True):
    __tablename__ = "inventories"
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
